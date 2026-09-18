"""绿地台账接口。"""

from flask import Blueprint, request

from ..errors import BadRequestError, DuplicateResourceError
from ..schemas import green_space_filters, validate_green_space
from ..services import GreenSpaceService
from ..utils.pagination import paginate, parse_page_args
from ..utils.requests import json_body, query_flag
from ..utils.responses import created, ok

bp = Blueprint("green_spaces", __name__)


@bp.get("/green-spaces")
def list_green_spaces():
    """台账列表：支持关键字、类型、等级、状态、行政区过滤 + 排序 + 分页。"""

    filters = green_space_filters(request.args)
    page, page_size = parse_page_args()
    query = GreenSpaceService.list_spaces(filters, request.args)
    data = paginate(query, page, page_size, serializer=GreenSpaceService.serialize_row)
    data["summary"] = GreenSpaceService.filtered_summary(filters)
    return ok(data)


@bp.get("/green-spaces/options")
def green_space_options():
    """下拉选项（仅未归档绿地）。"""

    keyword = (request.args.get("keyword") or "").strip() or None
    return ok({"items": GreenSpaceService.options(keyword=keyword)})


@bp.get("/green-spaces/districts")
def districts():
    return ok({"items": GreenSpaceService.districts()})


@bp.post("/green-spaces")
def create_green_space():
    """建档提交：同一行政区内存在名称/位置相近档案时返回 409 + 已存在档案列表，
    前端展示后由用户确认；确认无误可带 allow_duplicate=true 强制建档。"""

    body = json_body()
    payload = validate_green_space(body)
    if not body.get("allow_duplicate"):
        duplicates = GreenSpaceService.find_duplicates(
            payload.get("name"), payload.get("district"), payload.get("address")
        )
        if duplicates:
            raise DuplicateResourceError(
                f"同一行政区内已存在 {len(duplicates)} 处名称或位置相近的绿地档案，请核对是否重复建档",
                details={"duplicates": duplicates},
            )
    space = GreenSpaceService.create(payload)
    return created(space.to_dict(detail=True), message="绿地台账创建成功")


@bp.get("/green-spaces/<int:space_id>")
def get_green_space(space_id):
    return ok(GreenSpaceService.get(space_id).to_dict(detail=True))


@bp.get("/green-spaces/<int:space_id>/profile")
def green_space_profile(space_id):
    """绿地档案：台账信息 + 养护概览 + 近期任务/记录/更换。"""

    return ok(GreenSpaceService.detail(space_id))


@bp.put("/green-spaces/<int:space_id>")
def update_green_space(space_id):
    payload = validate_green_space(json_body())
    space = GreenSpaceService.update(space_id, payload)
    return ok(space.to_dict(detail=True), message="绿地台账已更新")


@bp.delete("/green-spaces/<int:space_id>")
def delete_green_space(space_id):
    """删除台账。存在关联业务数据时需显式 force=true 才会级联清理。"""

    force = query_flag("force")
    result = GreenSpaceService.delete(space_id, force=force)
    return ok(result, message="绿地台账及其关联数据已删除" if force else "绿地台账已删除")


@bp.post("/green-spaces/<int:space_id>/merge")
def merge_green_space(space_id):
    """合并重复档案：source_id 所指绿地的任务/记录/更换全部转移到本档案，
    源档案随后删除，原有业务数据全部保留。"""

    source_id = json_body().get("source_id")
    if not isinstance(source_id, int) or isinstance(source_id, bool):
        raise BadRequestError("请在请求体中指定要合并的绿地档案 source_id（整数）")
    result = GreenSpaceService.merge(space_id, source_id)
    moved = result["moved"]
    message = (
        "绿地档案合并完成，已转移养护任务 {maintenance_task} 项、养护记录 "
        "{maintenance_record} 条、绿植更换 {plant_replacement} 条"
    ).format(**moved)
    return ok(result, message=message)
