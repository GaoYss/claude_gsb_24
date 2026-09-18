"""绿地台账业务逻辑。"""

import re

from sqlalchemy import and_, func, or_

from ..constants import ENUM_GROUPS, GREEN_SPACE_STATUS
from ..errors import BadRequestError, ConflictError, DuplicateWarningError
from ..extensions import db
from ..models import GreenSpace, MaintenanceRecord, MaintenanceTask, PlantReplacement
from ..models.maintenance_task import OPEN_STATUSES
from ..utils.dates import format_date, today
from ..utils.numbers import to_float
from ..utils.sorting import parse_sort
from .base_service import BaseService
from .code_generator import year_prefix


class GreenSpaceService(BaseService):
    """绿地台账：建档、检索、档案聚合与删除保护。"""

    model = GreenSpace
    label = "绿地台账"
    code_field = "code"
    code_width = 4

    SORTABLE = {
        "code": GreenSpace.code,
        "name": GreenSpace.name,
        "area_sqm": GreenSpace.area_sqm,
        "established_date": GreenSpace.established_date,
        "created_at": GreenSpace.created_at,
    }

    @classmethod
    def code_prefix(cls):
        return year_prefix("GS")

    # ------------------------------------------------------------ 查询
    @staticmethod
    def _apply_filters(query, filters):
        if filters.get("green_type"):
            query = query.filter(GreenSpace.green_type == filters["green_type"])
        if filters.get("maintenance_grade"):
            query = query.filter(GreenSpace.maintenance_grade == filters["maintenance_grade"])
        if filters.get("status"):
            query = query.filter(GreenSpace.status == filters["status"])
        if filters.get("district"):
            query = query.filter(GreenSpace.district == filters["district"])
        keyword = filters.get("keyword")
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(
                or_(
                    GreenSpace.name.like(like),
                    GreenSpace.code.like(like),
                    GreenSpace.district.like(like),
                    GreenSpace.address.like(like),
                    GreenSpace.manager.like(like),
                )
            )
        return query

    @classmethod
    def list_spaces(cls, filters, args):
        """列表查询：用相关子查询带出各绿地的养护统计，避免 N+1。"""

        task_count = (
            db.select(func.count(MaintenanceTask.id))
            .where(MaintenanceTask.green_space_id == GreenSpace.id)
            .correlate(GreenSpace)
            .scalar_subquery()
        )
        open_task_count = (
            db.select(func.count(MaintenanceTask.id))
            .where(
                and_(
                    MaintenanceTask.green_space_id == GreenSpace.id,
                    MaintenanceTask.status.in_(OPEN_STATUSES),
                )
            )
            .correlate(GreenSpace)
            .scalar_subquery()
        )
        record_count = (
            db.select(func.count(MaintenanceRecord.id))
            .where(MaintenanceRecord.green_space_id == GreenSpace.id)
            .correlate(GreenSpace)
            .scalar_subquery()
        )
        replacement_count = (
            db.select(func.count(PlantReplacement.id))
            .where(PlantReplacement.green_space_id == GreenSpace.id)
            .correlate(GreenSpace)
            .scalar_subquery()
        )
        last_maintenance = (
            db.select(func.max(MaintenanceRecord.record_date))
            .where(MaintenanceRecord.green_space_id == GreenSpace.id)
            .correlate(GreenSpace)
            .scalar_subquery()
        )

        query = db.session.query(
            GreenSpace,
            task_count.label("task_count"),
            open_task_count.label("open_task_count"),
            record_count.label("record_count"),
            replacement_count.label("replacement_count"),
            last_maintenance.label("last_maintenance_date"),
        )
        query = cls._apply_filters(query, filters)
        query = query.order_by(parse_sort(args, cls.SORTABLE, GreenSpace.code.asc()))
        return query

    @classmethod
    def serialize_row(cls, row):
        space, task_count, open_task_count, record_count, replacement_count, last_date = row
        data = space.to_dict()
        data["statistics"] = {
            "task_count": task_count or 0,
            "open_task_count": open_task_count or 0,
            "record_count": record_count or 0,
            "replacement_count": replacement_count or 0,
            "last_maintenance_date": format_date(last_date),
        }
        return data

    @classmethod
    def filtered_summary(cls, filters):
        """当前筛选条件下的总量与总面积，供列表页顶部展示。"""

        total, area = cls._apply_filters(
            db.session.query(
                func.count(GreenSpace.id),
                func.coalesce(func.sum(GreenSpace.area_sqm), 0),
            ),
            filters,
        ).one()
        return {"total": total or 0, "total_area": to_float(area) or 0}

    @classmethod
    def options(cls, keyword=None, limit=50):
        """下拉选项：支持按名称/编号模糊搜索。"""

        query = db.session.query(GreenSpace).filter(
            GreenSpace.status != "archived"
        )
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(or_(GreenSpace.name.like(like), GreenSpace.code.like(like)))
        query = query.order_by(GreenSpace.code.asc()).limit(limit)
        return [item.to_brief() for item in query.all()]

    @classmethod
    def districts(cls):
        rows = (
            db.session.query(GreenSpace.district, func.count(GreenSpace.id))
            .group_by(GreenSpace.district)
            .order_by(GreenSpace.district.asc())
            .all()
        )
        return [{"district": district, "count": count} for district, count in rows]

    @classmethod
    def detail(cls, obj_id):
        """绿地详情：台账字段 + 养护概览 + 近期动态。"""

        space = cls.get(obj_id)
        record_stats = db.session.query(
            func.count(MaintenanceRecord.id),
            func.coalesce(func.sum(MaintenanceRecord.work_hours), 0),
            func.max(MaintenanceRecord.record_date),
        ).filter(MaintenanceRecord.green_space_id == space.id).one()

        replacement_stats = db.session.query(
            func.count(PlantReplacement.id),
            func.coalesce(func.sum(PlantReplacement.quantity), 0),
            func.coalesce(func.sum(PlantReplacement.amount), 0),
        ).filter(PlantReplacement.green_space_id == space.id).one()

        task_rows = (
            db.session.query(MaintenanceTask.status, func.count(MaintenanceTask.id))
            .filter(MaintenanceTask.green_space_id == space.id)
            .group_by(MaintenanceTask.status)
            .all()
        )
        task_status = {status: 0 for status in ENUM_GROUPS["task_status"].values}
        for status, count in task_rows:
            task_status[status] = count

        replacement_summary = db.session.query(
            PlantReplacement.reason,
            func.count(PlantReplacement.id),
            func.coalesce(func.sum(PlantReplacement.quantity), 0),
            func.coalesce(func.sum(PlantReplacement.amount), 0),
        ).filter(PlantReplacement.green_space_id == space.id).group_by(PlantReplacement.reason).all()

        recent_tasks = (
            db.session.query(MaintenanceTask)
            .filter(MaintenanceTask.green_space_id == space.id)
            .order_by(MaintenanceTask.plan_date.desc(), MaintenanceTask.id.desc())
            .limit(5)
            .all()
        )
        recent_records = (
            db.session.query(MaintenanceRecord)
            .filter(MaintenanceRecord.green_space_id == space.id)
            .order_by(MaintenanceRecord.record_date.desc(), MaintenanceRecord.id.desc())
            .limit(5)
            .all()
        )
        recent_replacements = (
            db.session.query(PlantReplacement)
            .filter(PlantReplacement.green_space_id == space.id)
            .order_by(PlantReplacement.replace_date.desc(), PlantReplacement.id.desc())
            .limit(5)
            .all()
        )

        return {
            "green_space": space.to_dict(detail=True),
            "statistics": {
                "record_count": record_stats[0] or 0,
                "total_work_hours": to_float(record_stats[1]) or 0,
                "last_maintenance_date": format_date(record_stats[2]),
                "replacement_count": replacement_stats[0] or 0,
                "replacement_quantity": to_float(replacement_stats[1]) or 0,
                "replacement_amount": to_float(replacement_stats[2]) or 0,
                "task_status": task_status,
                "is_maintenance_overdue": (
                    record_stats[2] is None or (today() - record_stats[2]).days > 30
                ),
            },
            "replacement_summary": [
                {
                    "reason": reason,
                    "reason_label": ENUM_GROUPS["replacement_reason"].label(reason),
                    "count": count,
                    "quantity": to_float(quantity) or 0,
                    "amount": to_float(amount) or 0,
                }
                for reason, count, quantity, amount in replacement_summary
            ],
            "recent_tasks": [item.to_dict() for item in recent_tasks],
            "recent_records": [item.to_dict() for item in recent_records],
            "recent_replacements": [item.to_dict() for item in recent_replacements],
        }

    # ------------------------------------------------------------ 重复检测
    # 名称/地址归一化后做相似度判定：完全相等、互相包含直接命中，
    # 否则按字符二元组 Jaccard 重合度阈值判定（地址噪声更大，阈值更高）。
    NAME_SIMILARITY = 0.5
    ADDRESS_SIMILARITY = 0.6
    _NORMALIZE_PATTERN = re.compile(r"[\s·,，。.、\-—_()（）【】\[\]#＃号]+")

    @classmethod
    def _normalize(cls, text):
        if not text:
            return ""
        return cls._NORMALIZE_PATTERN.sub("", str(text)).lower()

    @staticmethod
    def _bigrams(text):
        if len(text) < 2:
            return {text} if text else set()
        return {text[i:i + 2] for i in range(len(text) - 1)}

    @classmethod
    def _similar(cls, left, right, threshold):
        if not left or not right:
            return False
        if left == right:
            return True
        if len(left) >= 2 and len(right) >= 2 and (left in right or right in left):
            return True
        left_grams, right_grams = cls._bigrams(left), cls._bigrams(right)
        if not left_grams or not right_grams:
            return False
        return len(left_grams & right_grams) / len(left_grams | right_grams) >= threshold

    @classmethod
    def _related_counts(cls, space_id):
        """疑似重复提示中展示的关联数据量。"""

        return {
            "task_count": db.session.query(func.count(MaintenanceTask.id))
            .filter(MaintenanceTask.green_space_id == space_id).scalar() or 0,
            "record_count": db.session.query(func.count(MaintenanceRecord.id))
            .filter(MaintenanceRecord.green_space_id == space_id).scalar() or 0,
            "replacement_count": db.session.query(func.count(PlantReplacement.id))
            .filter(PlantReplacement.green_space_id == space_id).scalar() or 0,
        }

    @classmethod
    def find_duplicates(cls, *, name, district, address, exclude_id=None, limit=5):
        """同一行政区内名称或位置相近的绿地档案，按匹配原因返回。"""

        norm_name = cls._normalize(name)
        norm_address = cls._normalize(address)
        if not norm_name or not district:
            return []
        query = db.session.query(GreenSpace).filter(GreenSpace.district == district)
        if exclude_id is not None:
            query = query.filter(GreenSpace.id != exclude_id)
        matches = []
        for candidate in query.order_by(GreenSpace.code.asc()).all():
            reasons = []
            if cls._similar(norm_name, cls._normalize(candidate.name), cls.NAME_SIMILARITY):
                reasons.append("name")
            if norm_address and cls._similar(
                norm_address, cls._normalize(candidate.address), cls.ADDRESS_SIMILARITY
            ):
                reasons.append("address")
            if reasons:
                data = candidate.to_dict()
                data["match_reasons"] = reasons
                data["statistics"] = cls._related_counts(candidate.id)
                matches.append(data)
        return matches[:limit]

    @classmethod
    def ensure_not_duplicate(cls, payload, exclude_id=None):
        """建档/更新前的重复拦截：发现疑似重复档案时抛出 40901，由前端确认。"""

        if exclude_id is not None:
            current = cls.get(exclude_id)
            unchanged = (
                current.name == payload.get("name")
                and current.district == payload.get("district")
                and (current.address or "") == (payload.get("address") or "")
            )
            if unchanged:
                return
        duplicates = cls.find_duplicates(
            name=payload.get("name"),
            district=payload.get("district"),
            address=payload.get("address"),
            exclude_id=exclude_id,
        )
        if duplicates:
            raise DuplicateWarningError(
                f"所属行政区内已存在 {len(duplicates)} 处名称或位置相近的绿地档案，"
                "请确认是否重复建档",
                details={"duplicates": duplicates},
            )

    # ------------------------------------------------------------ 写入
    @classmethod
    def merge(cls, target_id, source_id):
        """合并重复档案：source 的全部任务/记录/更换迁移到 target 后删除 source。

        关联数据只做归属转移，不删任何业务记录；target 备注中追加合并说明留痕。
        """

        if not source_id:
            raise BadRequestError("请选择需要合并的绿地档案")
        if int(target_id) == int(source_id):
            raise BadRequestError("不能将绿地档案与自身合并")
        target = cls.get(target_id)
        source = cls.get(source_id)

        moved = {}
        for model, key in (
            (MaintenanceTask, "maintenance_task"),
            (MaintenanceRecord, "maintenance_record"),
            (PlantReplacement, "plant_replacement"),
        ):
            moved[key] = (
                db.session.query(model)
                .filter(model.green_space_id == source.id)
                .update({"green_space_id": target.id}, synchronize_session=False)
            )

        note = (
            f"已于 {today():%Y-%m-%d} 合并重复档案 {source.code}「{source.name}」"
            f"（{source.district}），其养护任务、记录与绿植更换全部并入本档案"
        )
        target.remark = f"{target.remark}\n{note}" if target.remark else note

        merged_brief = {"id": source.id, "code": source.code, "name": source.name}
        db.session.delete(source)
        db.session.commit()
        return {
            "target": target.to_dict(detail=True),
            "merged": merged_brief,
            "moved": moved,
        }

    @classmethod
    def delete(cls, obj_id, force=False):
        space = cls.get(obj_id)
        counts = {
            "maintenance_task": db.session.query(func.count(MaintenanceTask.id))
            .filter(MaintenanceTask.green_space_id == space.id)
            .scalar()
            or 0,
            "maintenance_record": db.session.query(func.count(MaintenanceRecord.id))
            .filter(MaintenanceRecord.green_space_id == space.id)
            .scalar()
            or 0,
            "plant_replacement": db.session.query(func.count(PlantReplacement.id))
            .filter(PlantReplacement.green_space_id == space.id)
            .scalar()
            or 0,
        }
        if sum(counts.values()) and not force:
            raise ConflictError(
                "该绿地已存在养护任务 {maintenance_task} 条、养护记录 {maintenance_record} 条、"
                "绿植更换记录 {plant_replacement} 条，删除将一并清除，请确认后重试".format(**counts),
                details=counts,
            )
        db.session.delete(space)
        db.session.commit()
        return counts

    @classmethod
    def status_summary(cls):
        rows = (
            db.session.query(GreenSpace.status, func.count(GreenSpace.id))
            .group_by(GreenSpace.status)
            .all()
        )
        summary = {code: 0 for code in GREEN_SPACE_STATUS.values}
        for status, count in rows:
            summary[status] = count
        return summary
