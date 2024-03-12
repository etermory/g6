import os
import re
from datetime import date, datetime, timedelta
from typing import Union, Optional, Tuple
from PIL import Image, UnidentifiedImageError

from fastapi import Request, UploadFile
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from core.models import Board, Config, Group, Member as MemberModel, Member
from core.database import DBConnect
from lib.common import is_none_datetime, get_img_path, delete_image


class MemberService(MemberModel):
    @classmethod
    def create_by_id(cls, db: Session, mb_id: str) -> MemberModel:
        query = select(cls).where(cls.mb_id == mb_id)

        return db.scalar(query)

    def is_intercept_or_leave(self) -> bool:
        """차단 또는 탈퇴한 회원인지 확인합니다.

        Returns:
            bool: 차단 또는 탈퇴한 회원이면 True, 아니거나 회원정보가 없으면 False
        """
        if not self.mb_id:
            return False

        return self.mb_leave_date or self.mb_intercept_date

    def is_email_certify(self, use_email_certify: bool) -> bool:
        """이메일 인증을 받았는지 확인합니다.
        Args:
            use_email_certify (bool): 이메일 인증을 사용하는지 여부

        Returns:
            bool: 이메일 인증을 받았으면 True, 아니면 False
        """
        if not use_email_certify:
            return True

        if not self.mb_id:
            return False

        return not is_none_datetime(self.mb_email_certify)


def get_member(mb_id: str) -> MemberModel:
    """회원 레코드 얻기
    -  fields: str = '*' # fields : 가져올 필드, 예) "mb_id, mb_name, mb_nick"

    Args:
        mb_id (str): 회원아이디

    Returns:
        Member: 회원 레코드
    """
    with DBConnect().sessionLocal() as db:
        member = db.scalar(select(MemberModel).filter_by(mb_id=mb_id))

    return member


def get_member_icon(request: Request, mb_id: str = None) -> str:
    """회원 아이콘 경로를 반환하는 함수

    Args:
        mb_id (str, optional): 회원아이디. Defaults to None.

    Returns:
        str: 회원 아이콘 경로
    """
    icon_dir = "data/member"
    image_path = get_img_path(request, icon_dir, mb_id)
    return image_path


def get_member_image(request: Request, mb_id: str = None) -> str:
    """회원 이미지 경로를 반환하는 함수

    Args:
        mb_id (str, optional): 회원아이디. Defaults to None.

    Returns:
        str: 회원 이미지 경로
    """
    image_dir = "data/member_image"
    image_path = get_img_path(request, image_dir, mb_id)
    return image_path


def validate_member_image(request: Request, img_file: UploadFile, img_type: str) -> Optional[Image.Image]:
    """
    멤버 이미지, 아이콘 파일 유효성 검사
    Args:
        request: FastAPI Request 객체
        img_file: 업로드할 이미지 파일
        img_type: 이미지 타입 (img, icon)
    Returns:
        Image.Image: PIL.Image.open()을 통해 얻어진 이미지 객체
    """

    if not img_file or not img_file.filename:
        return None
    
    from core.exception import AlertException
    config = request.state.config

    img_type_dict = {
        'icon': {
            'cf_size': 'cf_member_icon_size',
            'cf_width': 'cf_member_icon_width',
            'cf_height': 'cf_member_icon_height',
            'expr': '아이콘'
        },
        'img': {
            'cf_size': 'cf_member_img_size',
            'cf_width': 'cf_member_img_width',
            'cf_height': 'cf_member_img_height',
            'expr': '이미지'
        },
    }

    img_ext_regex = config.cf_image_extension
    img_ext_str = img_ext_regex.replace("|", ", ")
    
    try:
        img_file_info = Image.open(img_file.file)
    except UnidentifiedImageError:
        raise AlertException("이미지 파일이 아닙니다.", 400)

    width, height = img_file_info.size
    expr = img_type_dict[img_type]['expr']
    cf_size = getattr(config, img_type_dict[img_type]['cf_size'])
    cf_width = getattr(config, img_type_dict[img_type]['cf_width'])
    cf_height = getattr(config, img_type_dict[img_type]['cf_height'])

    if 0 < config.cf_member_img_size < img_file.size:
        raise AlertException(f"{expr} 용량은 {cf_size} 이하로 업로드 해주세요.", 400)

    if cf_width and cf_height:
        if width > cf_width or height > cf_height:
            raise AlertException(f"{expr} 크기는 {cf_width}x{cf_height} 이하로 업로드 해주세요.", 400)

    if not re.match(fr".*\.({img_ext_regex})$", img_file.filename, re.IGNORECASE):
        raise AlertException(f"{img_ext_str} 파일만 업로드 가능합니다.", 400)
    
    return img_file_info


def update_member_image(request: Request, upload_object: Optional[Image.Image], directory: str, filename: str, is_delete: Optional[int]):
    """멤버 이미지, 아이콘 파일 업데이트(업로드/수정/삭제)
    Args:
        request: FastAPI Request 객체)
        upload_object: 업로드할 이미지 객체 (Image.Image, PIL.Image.open()으로 얻어진 이미지 객체)
        filename: 저장할 파일명 (확장자 제외)
        is_delete: 이미지 삭제 여부
    """
    if is_delete or upload_object:
        # 기존 이미지 삭제
        img_ext_list = request.state.config.cf_image_extension.split("|")
        for ext in img_ext_list:
            delete_image(directory, f"{filename}.{ext}", True)
        if is_delete:
            return
    else:
        return

    # 이미지 저장 경로 생성
    os.makedirs(directory, exist_ok=True)

    # 이미지 저장 경로
    file_ext = upload_object.format.lower()
    save_path = os.path.join(directory, f"{filename}.{file_ext}")
    # 이미지 저장
    upload_object.save(save_path)
    upload_object.close()


def validate_and_update_member_image(
    request: Request,
    img_file: UploadFile,
    icon_file: UploadFile,
    filename: str,
    is_delete_img: Optional[int],
    is_delete_icon: Optional[int],
):
    """
    멤버 이미지, 아이콘 파일 유효성 검사 및 업데이트 통합 함수(업로드/수정/삭제)
    Args:
        request: FastAPI Request 객체
        img_file: 업로드할 이미지 파일
        icon_file: 업로드할 아이콘 파일
        filename: 저장할 파일명 (확장자 제외)
        is_delete_img: 이미지 삭제 여부
        is_delete_icon: 아이콘 삭제 여부
    """
    member_image_path = f"data/member_image/{filename[:2]}"
    member_icon_path = f"data/member/{filename[:2]}"
    mb_img_info = validate_member_image(request, img_file, 'img')
    mb_icon_info = validate_member_image(request, icon_file, 'icon')
    update_member_image(request, mb_img_info, member_image_path, filename, is_delete_img)
    update_member_image(request, mb_icon_info, member_icon_path, filename, is_delete_icon)


def get_member_level(request: Request) -> int:
    """request에서 회원 레벨 정보를 가져오는 함수"""
    member: MemberModel = request.state.login_member

    return int(member.mb_level) if member else 1


def get_admin_type(request: Request, mb_id: str = None,
                   group: Group = None, board: Board = None) -> Union[str, None]:
    """게시판 관리자 여부 확인 후 관리자 타입 반환
    - 그누보드5의 is_admin 함수를 참고하여 작성하려고 했으나, 이미 is_admin가 있어서 함수 이름을 변경함

    Args:
        request (Request): FastAPI Request 객체
        mb_id (str, optional): 회원 아이디. Defaults to None.
        group (Group, optional): 게시판 그룹 정보. Defaults to None.
        board (Board, optional): 게시판 정보. Defaults to None.

    Returns:
        Union[str, None]: 관리자 타입 (super, group, board, None)
    """
    if not mb_id:
        return None

    config = request.state.config
    group = group or (board.group if board else None)

    is_authority = None
    if config.cf_admin == mb_id:
        is_authority = "super"
    elif group and group.gr_admin == mb_id:
        is_authority = "group"
    elif board and board.bo_admin == mb_id:
        is_authority = "board"

    return is_authority


def is_super_admin(request: Request, mb_id: str = None) -> bool:
    """최고관리자 여부 확인

    Args:
        request (Request): FastAPI Request 객체
        mb_id (str, optional): 회원 아이디. Defaults to None.

    Returns:
        bool: 최고관리자이면 True, 아니면 False
    """
    config: Config = request.state.config
    cf_admin = str(config.cf_admin).lower().strip()

    if not cf_admin:
        return False

    mb_id = mb_id or request.session.get("ss_mb_id", "")
    if mb_id and mb_id.lower().strip() == cf_admin:
        return True

    return False


def is_email_registered(email: str, mb_id: str = None) -> bool:
    """이메일이 이미 등록되어 있는지 확인

    Args:
        email (str): 이메일 주소
        mb_id (str, optional): 회원 아이디. Defaults to None.
            회원정보 수정시 자신의 이메일을 제외하기 위해 사용

    Returns:
        bool: 이미 등록된 이메일이면 True, 아니면 False
    """
    query = exists(Member).where(Member.mb_email == email).select()
    if mb_id:
        query = query.where(Member.mb_id != mb_id)

    with DBConnect().sessionLocal() as db:
        exists_member = db.scalar(query)

    if exists_member:
        return True
    else:
        return False


def is_prohibit_email(request: Request, email: str):
    """금지된 메일인지 검사

    Args:
        request (Request): request 객체
        email (str): 이메일 주소

    Returns:
        bool: 금지된 메일이면 True, 아니면 False
    """
    config = request.state.config
    _, domain = email.split("@")

    # config에서 금지된 도메인 목록 가져오기
    cf_prohibit_email = getattr(config, "cf_prohibit_email", "")
    if cf_prohibit_email:
        prohibited_domains = [d.lower().strip() for d in cf_prohibit_email.split('\n')]

        # 주어진 도메인이 금지된 도메인 목록에 있는지 확인
        if domain.lower() in prohibited_domains:
            return True

    return False


def validate_mb_id(request: Request, mb_id: str) -> Tuple[bool, str]:
    """ 회원가입이 가능한 아이디인지 검사

    Args:
        request (Request): request 객체
        mb_id (str): 가입할 아이디

    Returns:
        Tuple[bool, str]: (검사 결과, 메시지)
    """
    config = request.state.config

    if not mb_id or mb_id.strip() == "":
        return False, "아이디를 입력해주세요."

    with DBConnect().sessionLocal() as db:
        exists_id = db.scalar(
            exists(Member).where(Member.mb_id == mb_id).select()
        )
    if exists_id:
        return False, "이미 가입된 아이디입니다."

    prohibited_ids = [id.strip() for id in getattr(config, "cf_prohibit_id", "").split(",")]
    if mb_id in prohibited_ids:
        return False, "사용할 수 없는 아이디입니다."

    return True, "사용 가능한 아이디입니다."


def validate_nickname(request: Request, mb_nick: str) -> Tuple[bool, str]:
    """ 등록 가능한 닉네임인지 검사

    Args:
        mb_nick : 등록할 닉네임
        prohibit_id : 금지된 닉네임

    Return:
        가능한 닉네임이면 True 아니면 에러메시지 배열

    """
    config = request.state.config

    if not mb_nick or mb_nick.strip() == "":
        return False, "닉네임을 입력해주세요."

    with DBConnect().sessionLocal() as db:
        exists_nickname = db.scalar(
            exists(Member).where(Member.mb_nick == mb_nick).select()
        )
    if exists_nickname:
        return False, "해당 닉네임이 존재합니다."

    if mb_nick in getattr(config, "cf_prohibit_id", "").strip():
        return False, "닉네임으로 정할 수 없는 단어입니다."

    return True, "사용 가능한 닉네임입니다."


def validate_nickname_change_date(before_nick_date: date, nick_modify_date: int) -> Tuple[bool, str]:
    """
        닉네임 변경 가능한지 날짜 검사
        Args:
            before_nick_date (datetime) : 이전 닉네임 변경한 날짜
            nick_modify_date (int) : 닉네임 수정가능일
        Raises:
            ValidationError: 닉네임 변경 가능일 안내
    """
    if not is_none_datetime(before_nick_date) and nick_modify_date != 0:
        available_date = before_nick_date + timedelta(days=nick_modify_date)
        if datetime.now().date() < available_date:
            return False, f"{available_date.strftime('%Y-%m-%d')} 이후 닉네임을 변경할 수 있습니다."

    return True, "닉네임을 변경할 수 있습니다."


def validate_email(request: Request, email: str) -> Tuple[bool, str]:
    """ 등록 가능한 이메일인지 검사

    Args:
        Request: request 객체
        email (str): 이메일 주소

    Returns:
        Tuple[bool, str]: (검사 결과, 메시지)

    """
    if not email or email.strip() == "":
        return False, "이메일을 입력해주세요."
    
    if is_email_registered(email):
        return False, "이미 가입된 이메일입니다."
    
    if is_prohibit_email(request, email):
        return False, "사용할 수 없는 이메일입니다."

    return True, "사용 가능한 이메일입니다."