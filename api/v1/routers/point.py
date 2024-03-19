from typing_extensions import Annotated

from fastapi import APIRouter, Depends

from core.models import Member
from lib.common import get_paging_info

from api.v1.dependencies.member import get_current_member
from api.v1.models import ViewPageModel, responses
from api.v1.models.point import ResponsePointListModel
from api.v1.lib.point import PointServiceAPI

router = APIRouter()


@router.get("/points",
            summary="회원 포인트 내역 목록 조회",
            response_model=ResponsePointListModel,
            responses={**responses})
async def read_member_points(
    current_member: Annotated[Member, Depends(get_current_member)],
    point_service: Annotated[PointServiceAPI, Depends()],
    data: Annotated[ViewPageModel, Depends()]
):
    """회원 포인트 내역을 조회합니다."""
    total_records = point_service.fetch_total_records(current_member)
    paging_info = get_paging_info(data.page, data.per_page, total_records)
    points = point_service.fetch_points(current_member, paging_info["offset"], data.per_page)

    return {
        "total_records": total_records,
        "total_pages": paging_info["total_pages"],
        "points": points
    }
