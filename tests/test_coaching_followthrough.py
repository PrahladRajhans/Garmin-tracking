import json
from datetime import UTC, date, datetime, timedelta

from garmin_mcp import coach_review, dashboard, db, reading_availability, wellness_review
from garmin_mcp.normalize import rebuild


def _brief(day, contribution):
    return {"day": day, "focus": {"title": "Keep today’s effort easy."},
            "readiness": {"ours": {"components": [{"contribution": contribution}],
                                  "composite_z": None}}, "sleep": {}}


def test_recovery_distinguishes_pending_sync_missing_and_incomplete(conn):
    rebuild(conn)
    day = "2026-11-25"
    previous = "2026-11-24"
    now = datetime(2026, 11, 25, 10, tzinfo=UTC)
    conn.execute("INSERT INTO daily(day, resting_hr) VALUES (?,44)", (previous,))
    conn.execute("INSERT INTO sleep(day,sleep_s) VALUES (?,3600)", (day,))
    conn.execute("INSERT INTO health_status(day,hrv) VALUES (?,43)", (day,))
    info = reading_availability.collect(conn, day, UTC, brief=_brief(day, -0.3), now=now)
    assert info["rows"]["sleep"]["state"] == "incomplete"
    assert info["rows"]["hrv"]["state"] == "recorded"
    assert info["rows"]["pulse"] == {"label": "Resting heart rate", "latest": previous,
                                     "state": "awaiting_sync"}
    assert info["usable"] == ["HRV over the last 7 days"]
    conn.execute("INSERT INTO meta VALUES ('last_full_sync','2026-11-25T02:00:00+00:00')")
    info = reading_availability.collect(conn, day, UTC, brief=_brief(day, -0.3), now=now)
    assert info["rows"]["pulse"]["state"] == "absent"
    assert "Latest usable reading" in dashboard._reading_availability_card({"reading_availability": info})
    info = reading_availability.collect(conn, day, UTC, brief=_brief(previous, -0.3), now=now, retry=True)
    assert not info["usable"] and not info["published_guidance"]


def test_nonfinite_and_nonnumeric_source_rows_do_not_count_as_usable(conn):
    rebuild(conn)
    day = "2026-11-25"
    now = datetime(2026, 11, 25, 10, tzinfo=UTC)
    conn.execute("INSERT INTO meta VALUES ('last_full_sync','2026-11-25T02:00:00+00:00')")
    conn.execute("INSERT INTO daily(day,resting_hr) VALUES (?,?)", (day, float("inf")))
    conn.execute("INSERT INTO sleep(day,sleep_s,avg_respiration) VALUES (?,'bad',-2)", (day,))
    conn.execute("INSERT INTO hrv(day,last_night_avg) VALUES (?,?)", (day, float("inf")))
    conn.execute("INSERT INTO readiness(day,score,level) VALUES (?,999,' ')", (day,))
    info = reading_availability.collect(conn, day, UTC, brief=_brief(day, None), now=now)
    assert all(row["state"] == "absent" for row in info["rows"].values())
    conn.execute("UPDATE readiness SET score=0 WHERE day=?", (day,))
    conn.execute("INSERT INTO health_status(day,respiration) VALUES (?,16)", (day,))
    info = reading_availability.collect(conn, day, UTC, brief=_brief(day, None), now=now)
    assert info["rows"]["garmin"]["state"] == info["rows"]["respiration"]["state"] == "recorded"


def test_audit_persists_only_published_decisions_and_explains_changed_reasons(conn):
    day = "2026-11-25"
    focus = {"title": "Keep it easy", "detail": "Sleep was shorter.", "evidence_keys": ("sleep_week",)}
    brief = {"focus": focus}
    signals = {"sleep_h": {"unit": "h", "label": "Sleep duration", "recent": 6.2, "previous": 7.1,
                           "recent_count": 5, "previous_count": 7}}
    evidence = coach_review.decision_evidence(day, brief, signals)
    assert "6.2 h from 5 readings" in evidence[0]["detail"]
    coach_review.guidance(conn, day, focus, evidence=evidence, save=True)
    updated = {**focus, "detail": "Garmin marked readiness low."}
    preview = coach_review.guidance(conn, day, updated)
    assert preview["previous"]["evidence"] == evidence
    old = json.loads(conn.execute("SELECT value FROM meta WHERE key='dashboard_guidance'").fetchone()[0])
    assert len(old["history"]) == 1
    coach_review.guidance(conn, day, updated, save=True)
    coach_review.guidance(conn, day, updated, save=True)
    result = json.loads(conn.execute("SELECT value FROM meta WHERE key='dashboard_guidance'").fetchone()[0])
    assert [row["detail"] for row in result["history"]] == [focus["detail"], updated["detail"]]


def test_body_battery_uses_recorded_days_and_nap_zero_is_distinct_from_missing(conn):
    rebuild(conn)
    end = date(2026, 11, 25)
    for i in range(1, 9):
        stamp = (end - timedelta(days=i)).isoformat()
        conn.execute("INSERT INTO daily(day,body_battery_charged,body_battery_drained) VALUES (?,?,?)",
                     (stamp, 30 if i <= 4 else 45, 80 if i <= 4 else 50))
        conn.execute("INSERT INTO sleep(day,sleep_s,sleep_need_min) VALUES (?,?,480)",
                     (stamp, 21600 if i <= 4 else 28800))
        if i <= 4:
            db.upsert_activity(conn, {"activityId": i, "startTimeLocal": f"{stamp}T07:00:00",
                                      "activityType": {"typeKey": "running"}})
    day = end.isoformat()
    db.put_daily(conn, "pa_sleep", day, "personal_api",
                 {"dailySleepDTO": {"calendarDate": day, "napTimeSeconds": 0}})
    db.put_daily(conn, "sleep", day, "garminconnect",
                 {"dailySleepDTO": {"calendarDate": day, "napTimeSeconds": 1200}})
    previous = (end - timedelta(days=1)).isoformat()
    db.put_range(conn, "pa_sleep_summaries", previous, day, "personal_api",
                 [{"calendarDate": previous, "napTimeSeconds": 1800}])
    review = wellness_review.collect(conn, day)
    assert review["sleep_compare"] == {"first": 30, "second": 45, "first_count": 4, "second_count": 4}
    assert review["run_compare"]["second"] == 80
    assert review["nap_compare"] is None
    assert (review["nap_days"], review["nap_positive_days"], review["latest_nap_s"]) == (2, 1, 0)
    assert "zero nap minutes" in dashboard._nap_note(review)
    assert "80 vs 50 points" in dashboard._wellness_recovery_card(review)


def test_weekly_cue_revisits_logged_outcomes_and_respects_daily_pause():
    d = {"trial": {"active": True, "trial": {"kind": "cadence"},
                   "attempts": [{"changes": [{"metric": "efficiency_factor"}]}, {}],
                   "next": "Repeat at the same pace."},
         "brief": {"focus": {"title": "Keep it easy"}}}
    assert "1 with a comparable effort reading" in dashboard._weekly_cue_review(d)
    assert "Repeat at the same pace." in dashboard._weekly_cue_review(d)
    d["brief"]["knee_pause"] = True
    assert "Pause the experiment" in dashboard._weekly_cue_review(d)
    d["sync_retry_required"] = True
    assert dashboard._weekly_cue_review(d) == ""
