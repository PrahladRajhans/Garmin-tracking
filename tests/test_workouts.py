from garmin_mcp import workouts


class FakeClient:
    def __init__(self):
        self.uploaded = None
        self.scheduled = None

    def upload_workout(self, payload):
        self.uploaded = payload
        return {"workoutId": 7}

    def schedule_workout(self, wid, day):
        self.scheduled = (wid, day)

    def get_workouts(self, start, limit):
        return [{"workoutId": 7, "workoutName": "x", "sportType": {"sportTypeKey": "running"}}]

    def delete_workout(self, wid):
        self.deleted = wid


SPEC = {"name": "5x800", "steps": [
    {"type": "warmup", "duration": "10:00"},
    {"type": "repeat", "times": 5, "steps": [
        {"type": "interval", "distance_m": 800, "pace": "5:00-5:10"},
        {"type": "recovery", "duration": "2:00"}]},
    {"type": "cooldown", "duration": "10:00"}]}


def test_build_converts_units_and_structure():
    out = workouts.build(SPEC)
    steps = out["workoutSegments"][0]["workoutSteps"]
    assert steps[0]["endConditionValue"] == 600
    rep = steps[1]
    assert rep["numberOfIterations"] == 5
    interval = rep["workoutSteps"][0]
    # pace target in m/s: 5:10 -> 1000/310 (slow, lower), 5:00 -> 1000/300 (fast, upper)
    assert abs(interval["targetValueOne"] - 1000 / 310) < 1e-6
    assert abs(interval["targetValueTwo"] - 1000 / 300) < 1e-6
    assert interval["endConditionValue"] == 800
    assert [s["stepOrder"] for s in steps] == [1, 2, 5]


def test_distance_based_warmup_keeps_its_step_type():
    spec = {"steps": [{"type": "warmup", "distance_m": 800}]}
    assert not workouts.validate(spec, 188)
    step = workouts.build(spec)["workoutSegments"][0]["workoutSteps"][0]
    assert step["stepType"]["stepTypeKey"] == "warmup"
    assert step["endCondition"]["conditionTypeKey"] == "distance"


def test_validation_catches_unsafe_targets():
    bad = {"steps": [{"type": "interval", "duration": "5:00", "hr": "150-230"},
                     {"type": "interval", "distance_m": 400, "pace": "1:30-2:00"},
                     {"type": "sprint", "duration": "1:00"}]}
    problems = workouts.validate(bad, hr_max=193)
    assert any("above your max HR" in p for p in problems)
    assert any("outside 2:30-12:00" in p for p in problems)
    assert any("unknown step type" in p for p in problems)
    assert workouts.validate(SPEC, 193) == []


def test_upload_schedule_list_delete_with_fake_client(conn):
    conn.execute("INSERT INTO activities(activity_id, type, start_time_local, max_hr, updated_at)"
                 " VALUES (1, 'running', '2026-11-20 07:00:00', 190, 'x')")
    conn.commit()
    f = FakeClient()
    r = workouts.create(conn, SPEC, upload=True, schedule_date="2026-11-25", client=f)
    assert r["uploaded"] and r["workout_id"] == 7 and f.scheduled == (7, "2026-11-25")
    assert workouts.list_on_garmin(f)["workouts"][0]["id"] == 7
    assert workouts.delete_on_garmin(7, f) == {"deleted": 7}


def test_workout_upload_without_valid_id_is_unverified_and_never_schedules(conn):
    for reply in (None, {}, {"workoutId": 0}, {"workoutId": True}, {"workoutId": "unknown"}):
        fake = FakeClient()
        fake.upload_workout = lambda payload, reply=reply: reply
        result = workouts.create(conn, SPEC, upload=True, schedule_date="2026-11-25", client=fake)
        assert not result["uploaded"] and result["upload_status"] == "unverified"
        assert "Check your saved workouts" in result["next"]
        assert fake.scheduled is None


def test_workout_calendar_error_preserves_acknowledged_upload(conn):
    fake = FakeClient()

    def fail_schedule(*args):
        raise TimeoutError("private API response")

    fake.schedule_workout = fail_schedule
    result = workouts.create(conn, SPEC, upload=True, schedule_date="2026-11-25", client=fake)
    assert result["uploaded"] and result["workout_id"] == 7
    assert result["schedule_status"] == "unverified" and result["schedule_error"] == "TimeoutError"
    assert "scheduled_for" not in result and "private API response" not in repr(result)


def test_malformed_workouts_return_problems_instead_of_crashing():
    from garmin_mcp import workouts

    bad_steps = [
        {"type": "interval", "duration": "0:00"},
        {"type": "interval", "duration": "5:99"},
        {"type": "interval", "distance_m": -100},
        {"type": "interval", "duration": 60, "pace": "bad"},
        {"type": "interval", "duration": 60, "pace": 310},
        {"type": "interval", "duration": 60, "hr": "140-120"},
        {"type": "interval", "duration": 60, "hr_zone": 2.5},
        {"type": "repeat", "times": "not a number", "steps": []},
        1,
    ]
    for step in bad_steps:
        assert workouts.validate({"steps": [step]}, 188)
    cyclic = {"type": "repeat", "times": 2, "steps": []}
    cyclic["steps"].append(cyclic)
    assert workouts.validate({"steps": [cyclic]}, 188)
    assert workouts.validate({"steps": [{"type": "interval", "duration": 60}] * 201}, 188)


def test_preview_shows_nested_repeat_order_and_progressive_pace_without_connect(conn, monkeypatch):
    from garmin_mcp import client

    def unexpected_login():
        raise AssertionError("preview must never load a Garmin client")

    monkeypatch.setattr(client, "get_client", unexpected_login)
    spec = {"name": "Progression", "steps": [
        {"type": "warmup", "duration": 180, "hr_zone": 2},
        {"type": "repeat", "times": 3, "steps": [
            {"type": "interval", "distance_m": 1000, "pace": "5:45-5:30"},
            {"type": "repeat", "times": 2, "steps": [
                {"type": "interval", "distance_m": 400, "pace": "5:00-5:10"},
                {"type": "recovery", "duration": 30, "hr": "120-140"}]},
        ]},
        {"type": "cooldown", "duration": 120},
    ]}
    result = workouts.create(conn, spec, schedule_date="2026-11-26")
    assert result["ok"] and result["uploaded"] is False
    preview = result["preview"]
    assert preview["requested_schedule_date"] == "2026-11-26"
    assert preview["totals"] == {
        "encoded_steps": 7, "performed_steps": 17, "repeat_depth": 2,
        "fixed_time_s": 480, "fixed_distance_m": 5400, "distance_without_pace_m": 0,
    }
    assert preview["time_at_target_range_s"] == [2190, 2259]
    warmup, outer, cooldown = preview["steps"]
    assert [s["order"] for s in (warmup, outer, cooldown)] == [1, 2, 7]
    assert warmup["target"] == {"heart_rate_zone": 2}
    longer, inner = outer["steps"]
    faster, recovery = inner["steps"]
    assert outer["times"] == 3 and inner["times"] == 2
    assert [s["order"] for s in (longer, inner, faster, recovery)] == [3, 4, 5, 6]
    assert longer["target"] == {"pace": "5:30–5:45 min/km", "faster_s_per_km": 330,
                                "slower_s_per_km": 345}
    assert faster["target"] == {"pace": "5:00–5:10 min/km", "faster_s_per_km": 300,
                                "slower_s_per_km": 310}
    assert recovery["target"] == {"min_bpm": 120, "max_bpm": 140}
    assert preview["compatibility"]["watch_status"] == "unverified"
    assert {"nested_repeats", "heart_rate_zones"} <= preview["compatibility"].keys()


def test_preview_leaves_time_range_unknown_when_any_distance_has_no_pace(conn):
    spec = {"steps": [{"type": "warmup", "distance_m": 500}, *SPEC["steps"]]}
    result = workouts.create(conn, spec)
    preview = result["preview"]
    assert preview["totals"]["fixed_distance_m"] == 4500
    assert preview["totals"]["distance_without_pace_m"] == 500
    assert preview["time_at_target_range_s"] is None
    assert result["estimated_duration_s"] > preview["totals"]["fixed_time_s"]


def test_repeat_and_schedule_errors_prevent_upload(conn):
    fake = FakeClient()
    extra_target = {"type": "repeat", "times": 2, "pace": "5:00-5:10", "steps": SPEC["steps"]}
    stray_repeat = {"type": "interval", "duration": 60, "times": 3}
    assert workouts.validate({"steps": [extra_target]}, 188)
    assert workouts.validate({"steps": [stray_repeat]}, 188)
    result = workouts.create(conn, SPEC, upload=True, schedule_date="2026-W48-4", client=fake)
    assert result == {"ok": False, "problems": ["schedule date must be YYYY-MM-DD"]}
    assert fake.uploaded is None and fake.scheduled is None


def test_repeat_limits_and_nonfinite_workout_totals(conn):
    step = {"type": "interval", "duration": 4}
    for times in (1, 30):
        result = workouts.create(conn, {"steps": [{"type": "repeat", "times": times, "steps": [step]}]})
        assert result["preview"]["totals"]["performed_steps"] == times
        assert result["preview"]["time_at_target_range_s"] == [times * 4, times * 4]
    for times in (0, 31):
        assert workouts.validate({"steps": [{"type": "repeat", "times": times, "steps": [step]}]}, 188)
    huge = {"steps": [{"type": "repeat", "times": 3, "steps": [{"type": "interval", "duration": 1e308}]}]}
    assert workouts.create(conn, huge)["problems"] == ["combined workout duration must be finite"]


def test_workout_router_dispatches_only_supported_actions(monkeypatch):
    from garmin_mcp import server

    calls = []
    monkeypatch.setattr(workouts, "list_on_garmin", lambda: calls.append("list") or {"workouts": []})
    monkeypatch.setattr(workouts, "delete_on_garmin", lambda workout_id: calls.append(workout_id) or
                        {"deleted": workout_id})

    assert server.garmin_workouts("delte") == {"error": "action must be list or delete"}
    assert server.garmin_workouts("delete") == {"error": "workout_id required"}
    assert calls == []
    assert server.garmin_workouts() == {"workouts": []}
    assert server.garmin_workouts("delete", workout_id=55) == {"deleted": 55}
    assert calls == ["list", 55]
