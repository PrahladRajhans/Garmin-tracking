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
def test_malformed_workouts_return_problems_instead_of_crashing():
    from garmin_mcp import workouts

    bad_steps = [
        {"type": "interval", "duration": "0:00"},
        {"type": "interval", "duration": "5:99"},
        {"type": "interval", "distance_m": -100},
        {"type": "interval", "duration": 60, "pace": "bad"},
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
