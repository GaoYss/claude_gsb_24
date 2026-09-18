"""绿地建档查重与档案合并测试。"""

from datetime import date


def space_payload(**overrides):
    payload = {
        "name": "运河文化公园",
        "district": "拱墅区",
        "address": "运河东路 128 号",
        "green_type": "park",
        "maintenance_grade": "level1",
        "area_sqm": 46200,
    }
    payload.update(overrides)
    return payload


def test_same_name_same_district_is_flagged(api):
    api.data(api.post("/api/v1/green-spaces", space_payload()), 201)

    response = api.post("/api/v1/green-spaces", space_payload(address="运河东路 200 号"))
    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == 40901
    duplicates = body["data"]["duplicates"]
    assert len(duplicates) == 1
    assert duplicates[0]["name"] == "运河文化公园"
    assert "名称相同" in duplicates[0]["match_reasons"]
    assert duplicates[0]["similarity"] >= 75


def test_similar_name_is_flagged(api):
    api.data(api.post("/api/v1/green-spaces", space_payload()), 201)

    response = api.post("/api/v1/green-spaces", space_payload(name="运河文化公园东区"))
    assert response.status_code == 409
    reasons = response.get_json()["data"]["duplicates"][0]["match_reasons"]
    assert "名称高度相似" in reasons


def test_same_address_with_close_name_is_flagged(api):
    api.data(api.post("/api/v1/green-spaces", space_payload(
        name="滨河绿地", address="滨河路 10 号",
    ),), 201)

    # 地址完全相同、名称中等相似
    response = api.post("/api/v1/green-spaces", space_payload(
        name="滨河公园", address="滨河路 10 号",
    ))
    assert response.status_code == 409
    reasons = response.get_json()["data"]["duplicates"][0]["match_reasons"]
    assert "地址相同" in reasons

    # 名称与地址都中等相近
    response = api.post("/api/v1/green-spaces", space_payload(
        name="滨河公园", address="滨河路 12 号",
    ))
    assert response.status_code == 409
    reasons = response.get_json()["data"]["duplicates"][0]["match_reasons"]
    assert "名称与地址相近" in reasons


def test_same_name_in_other_district_passes(api):
    api.data(api.post("/api/v1/green-spaces", space_payload()), 201)
    data = api.data(api.post("/api/v1/green-spaces", space_payload(district="西湖区")), 201)
    assert data["district"] == "西湖区"


def test_distinct_space_passes(api):
    api.data(api.post("/api/v1/green-spaces", space_payload()), 201)
    data = api.data(api.post("/api/v1/green-spaces", space_payload(
        name="城北体育公园", address="绍兴路 400 号",
    )), 201)
    assert data["name"] == "城北体育公园"


def test_allow_duplicate_bypasses_check(api):
    api.data(api.post("/api/v1/green-spaces", space_payload()), 201)
    payload = space_payload()
    payload["allow_duplicate"] = True
    data = api.data(api.post("/api/v1/green-spaces", payload), 201)
    assert data["name"] == "运河文化公园"


def test_merge_moves_all_related_data(api, make_space, make_task, make_record, make_replacement):
    target = make_space(name="目标绿地")
    source = make_space(name="源绿地")
    task = make_task(space=source)
    record = make_record(task=task)
    make_replacement(space=source, record=record)

    data = api.data(api.post(
        f"/api/v1/green-spaces/{target.id}/merge", {"source_id": source.id}
    ))
    assert data["merged_from"] == {"id": source.id, "code": source.code, "name": "源绿地"}
    assert data["moved"] == {
        "maintenance_task": 1,
        "maintenance_record": 1,
        "plant_replacement": 1,
    }
    assert data["target"]["id"] == target.id

    # 源档案已删除，业务数据全部转移到目标档案
    assert api.get(f"/api/v1/green-spaces/{source.id}").status_code == 404
    profile = api.data(api.get(f"/api/v1/green-spaces/{target.id}/profile"))
    assert profile["statistics"]["record_count"] == 1
    assert profile["statistics"]["replacement_count"] == 1
    assert profile["statistics"]["task_status"]["completed"] == 1

    task_data = api.data(api.get(f"/api/v1/maintenance-tasks/{task.id}"))
    assert task_data["green_space_id"] == target.id
    record_data = api.data(api.get(f"/api/v1/maintenance-records/{record.id}"))
    assert record_data["green_space_id"] == target.id


def test_merge_fills_blank_fields_of_target(api, make_space):
    target = make_space(name="目标绿地", manager=None)
    source = make_space(
        name="源绿地", address="文一西路 100 号", manager="沈建国",
        remark="2025 年移交",
    )

    data = api.data(api.post(
        f"/api/v1/green-spaces/{target.id}/merge", {"source_id": source.id}
    ))
    assert set(data["filled_fields"]) == {"address", "manager", "remark"}
    assert data["target"]["address"] == "文一西路 100 号"
    assert data["target"]["manager"] == "沈建国"

    # 目标已有值的字段不被覆盖
    source2 = make_space(name="源绿地二", manager="不应覆盖")
    data = api.data(api.post(
        f"/api/v1/green-spaces/{target.id}/merge", {"source_id": source2.id}
    ))
    assert data["target"]["manager"] == "沈建国"
    assert "manager" not in data["filled_fields"]


def test_merge_rejects_invalid_requests(api, make_space):
    space = make_space(name="目标绿地")

    response = api.post(f"/api/v1/green-spaces/{space.id}/merge", {"source_id": space.id})
    assert response.status_code == 400

    response = api.post(f"/api/v1/green-spaces/{space.id}/merge", {})
    assert response.status_code == 400

    response = api.post(f"/api/v1/green-spaces/{space.id}/merge", {"source_id": 99999})
    assert response.status_code == 404

    other = make_space(name="其他绿地")
    response = api.post(f"/api/v1/green-spaces/99999/merge", {"source_id": other.id})
    assert response.status_code == 404


def test_merged_space_keeps_working_for_new_business(api, make_space, make_task):
    """合并后的档案仍可正常登记新任务。"""

    target = make_space(name="目标绿地")
    source = make_space(name="源绿地")
    make_task(space=source)
    api.data(api.post(f"/api/v1/green-spaces/{target.id}/merge", {"source_id": source.id}))

    data = api.data(api.post("/api/v1/maintenance-tasks", {
        "green_space_id": target.id,
        "title": "合并后首次修剪",
        "task_type": "prune",
        "plan_date": str(date(2026, 4, 1)),
        "priority": "medium",
    }), 201)
    assert data["green_space_id"] == target.id
