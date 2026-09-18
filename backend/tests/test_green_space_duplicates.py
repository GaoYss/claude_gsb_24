"""绿地建档重复提示与档案合并测试。"""

from datetime import date


def space_payload(**overrides):
    payload = {
        "name": "运河文化公园",
        "district": "拱墅区",
        "address": "运河东路 128 号",
        "green_type": "park",
        "maintenance_grade": "level1",
        "area_sqm": 46200,
        "manager": "俞晓慧",
    }
    payload.update(overrides)
    return payload


def test_create_same_name_same_district_warns_duplicate(api):
    api.post("/api/v1/green-spaces", space_payload())

    response = api.post("/api/v1/green-spaces", space_payload(name="运河文化公园", address=""))
    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == 40901
    duplicates = body["data"]["duplicates"]
    assert len(duplicates) == 1
    assert duplicates[0]["name"] == "运河文化公园"
    assert duplicates[0]["match_reasons"] == ["name"]
    assert "statistics" in duplicates[0]


def test_create_similar_name_and_address_warns_duplicate(api):
    api.post("/api/v1/green-spaces", space_payload(name="滨江绿苑", address="江南大道 500 号"))

    # 名称高度相近（仅一字之差）
    response = api.post("/api/v1/green-spaces", space_payload(name="滨江绿园", address=""))
    assert response.status_code == 409
    assert response.get_json()["data"]["duplicates"][0]["match_reasons"] == ["name"]

    # 名称不同但地址相同，视为位置相近
    response = api.post(
        "/api/v1/green-spaces", space_payload(name="江畔口袋公园", address="江南大道500号")
    )
    assert response.status_code == 409
    assert response.get_json()["data"]["duplicates"][0]["match_reasons"] == ["address"]


def test_create_allows_distinct_or_other_district(api):
    api.post("/api/v1/green-spaces", space_payload())

    # 同区但名称、地址均不相近
    response = api.post("/api/v1/green-spaces", space_payload(name="城西生态游园", address="文一西路 1 号"))
    assert response.status_code == 201

    # 不同行政区即使同名也不提示
    response = api.post("/api/v1/green-spaces", space_payload(district="西湖区"))
    assert response.status_code == 201


def test_create_with_allow_duplicate_flag_bypasses_warning(api):
    api.post("/api/v1/green-spaces", space_payload())

    data = api.data(
        api.post("/api/v1/green-spaces?allow_duplicate=true", space_payload()), 201
    )
    assert data["name"] == "运河文化公园"


def test_update_warns_duplicate_but_excludes_self(api, make_space):
    make_space(name="滨江绿苑", district="滨江区", address="江南大道 500 号")
    space = make_space(name="江畔公园", district="滨江区")

    # 更新自身（名称/地址/行政区未变）不触发检测
    response = api.put(f"/api/v1/green-spaces/{space.id}", space_payload(
        name="江畔公园", district="滨江区", manager="新负责人"))
    assert response.status_code == 200

    # 改名后与已有档案相近 → 提示
    response = api.put(f"/api/v1/green-spaces/{space.id}", space_payload(
        name="滨江绿园", district="滨江区", address=""))
    assert response.status_code == 409
    assert response.get_json()["code"] == 40901

    # 确认后重试放行
    data = api.data(api.put(
        f"/api/v1/green-spaces/{space.id}?allow_duplicate=true",
        space_payload(name="滨江绿园", district="滨江区", address=""),
    ))
    assert data["name"] == "滨江绿园"


def test_merge_moves_all_related_data_and_removes_source(api, make_space, make_task,
                                                         make_record, make_replacement):
    target = make_space(name="运河文化公园", district="拱墅区")
    source = make_space(name="运河文化公园东园", district="拱墅区")
    task = make_task(space=source)
    record = make_record(task=task, work_hours=8)
    make_record(space=source, work_hours=4, record_date=date(2026, 4, 1))
    replacement = make_replacement(space=source, quantity=10)

    data = api.data(api.post(f"/api/v1/green-spaces/{target.id}/merge",
                             {"source_id": source.id}))
    assert data["merged"]["code"] == source.code
    assert data["moved"] == {
        "maintenance_task": 1,
        "maintenance_record": 2,
        "plant_replacement": 1,
    }
    assert "合并重复档案" in data["target"]["remark"]

    # 原档案已删除，任务/记录/更换全部保留并归属目标绿地
    assert api.get(f"/api/v1/green-spaces/{source.id}").status_code == 404

    task_data = api.data(api.get(f"/api/v1/maintenance-tasks/{task.id}"))
    assert task_data["green_space_id"] == target.id

    record_data = api.data(api.get(f"/api/v1/maintenance-records/{record.id}"))
    assert record_data["green_space_id"] == target.id
    assert record_data["task_id"] == task.id

    replacement_data = api.data(api.get(f"/api/v1/plant-replacements/{replacement.id}"))
    assert replacement_data["green_space_id"] == target.id

    profile = api.data(api.get(f"/api/v1/green-spaces/{target.id}/profile"))
    assert profile["statistics"]["record_count"] == 2
    assert profile["statistics"]["total_work_hours"] == 12.0
    assert profile["statistics"]["replacement_count"] == 1


def test_merge_keeps_target_existing_data(api, make_space, make_task, make_record):
    target = make_space(name="中心公园", district="西湖区")
    source = make_space(name="中心公园北园", district="西湖区")
    make_task(space=target)
    make_record(space=target, work_hours=2)
    make_task(space=source)

    data = api.data(api.post(f"/api/v1/green-spaces/{target.id}/merge",
                             {"source_id": source.id}))
    assert data["moved"]["maintenance_task"] == 1

    profile = api.data(api.get(f"/api/v1/green-spaces/{target.id}/profile"))
    assert profile["statistics"]["task_status"]["pending"] == 2
    assert profile["statistics"]["record_count"] == 1


def test_merge_validates_input(api, make_space):
    space = make_space()

    response = api.post(f"/api/v1/green-spaces/{space.id}/merge", {})
    assert response.status_code == 400

    response = api.post(f"/api/v1/green-spaces/{space.id}/merge", {"source_id": space.id})
    assert response.status_code == 400

    response = api.post(f"/api/v1/green-spaces/{space.id}/merge", {"source_id": 99999})
    assert response.status_code == 404

    response = api.post("/api/v1/green-spaces/99999/merge", {"source_id": space.id})
    assert response.status_code == 404
