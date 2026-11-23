"""Phase 9: static personal dashboard (one HTML file, data embedded, Chart.js from a CDN).

Built from the same functions the MCP tools use, so the dashboard and Claude always agree.
Garmin's own values carry a "G" badge and are never blended with ours.
Output: $GARMIN_DATA_DIR/dashboard/index.html (open in any browser; works on a phone).
"""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from garmin_mcp import coaching, engine, insights, loads, recovery

CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"


def collect(conn: sqlite3.Connection, end: str | None = None) -> dict[str, Any]:
    end = end or insights._latest_day(conn)
    e = date.fromisoformat(end)
    lo90 = (e - timedelta(days=89)).isoformat()
    brief = insights.daily_brief(conn, end)
    feed = engine.insight_feed(conn, end)
    rt = recovery.recovery_trend(conn, end, 60)["days"]
    hrv_series = [{"day": d, "hrv": v} for d, v in conn.execute(
        "SELECT day, COALESCE(h.last_night_avg, s.hrv) FROM health_status s LEFT JOIN hrv h "
        "USING(day) WHERE day >= ? AND day <= ? ORDER BY day",
        ((e - timedelta(days=59)).isoformat(), end))]
    fitness = [dict(zip(("day", "ctl", "atl", "tsb", "load"), r)) for r in conn.execute(
        "SELECT day, ctl, atl, tsb, load FROM fitness WHERE day BETWEEN ? AND ? ORDER BY day",
        (lo90, end))]
    garmin_acute = dict(conn.execute("SELECT day, acute_load FROM training WHERE day BETWEEN ? "
                                     "AND ?", (lo90, end)))
    sleep = [dict(zip(("day", "h", "score"), r)) for r in conn.execute(
        "SELECT day, ROUND(sleep_s/3600.0, 2), score FROM sleep WHERE day BETWEEN ? AND ? "
        "AND sleep_s >= 3*3600 ORDER BY day",  # < 3 h = incomplete record
        ((e - timedelta(days=59)).isoformat(), end))]
    rhr = [dict(zip(("day", "rhr"), r)) for r in conn.execute(
        "SELECT day, resting_hr FROM daily WHERE day BETWEEN ? AND ? AND resting_hr IS NOT NULL "
        "ORDER BY day", ((e - timedelta(days=59)).isoformat(), end))]
    perf = loads.race_predictions(conn, end, 180)
    curve = loads.pace_curve(conn, end, 365)["curve"]
    runs = []
    for aid, start in conn.execute(
            "SELECT activity_id, start_time_local FROM activities WHERE type LIKE '%run%' "
            "ORDER BY start_time_local DESC LIMIT 8"):
        m = coaching.run_metrics(conn, aid)
        if m:
            runs.append({"date": start[:10], "km": round(m["moving_s"] * m["avg_speed"] / 1000, 2),
                         "pace": coaching._pace(m["avg_speed"]), "hr": m["avg_hr"],
                         "ef": m["efficiency_factor"], "decoupling": m["decoupling_pct"],
                         "cadence": m["cadence_spm"], "gct": m["ground_contact_ms"],
                         "vr": m["vertical_ratio_pct"]})
    return {
        "end": end, "brief": brief, "feed": feed["insights"], "recovery": rt,
        "hrv": hrv_series, "fitness": fitness, "garmin_acute": garmin_acute, "sleep": sleep,
        "rhr": rhr, "predictions": perf, "curve": curve, "runs": runs,
        "weekly": insights.weekly_review(conn, end),
        "ranges": engine.personal_ranges(conn, end), "form": engine.form_percent(conn, end),
        "relationships": engine.relationships(conn, end, 365)["notable"],
        "trends": engine.trends(conn, end, 90)["trends"],
        "calendar": engine.calendar(conn, end, 182)["days"],
        "thresholds": loads.thresholds(conn, end),
        "fitness_age": coaching.fitness_age(conn),
        "swims": coaching.swim_trends(conn, end, 365)["sessions"][-6:],
        "strength": coaching.strength_trends(conn, end, 365)["monthly"][-6:],
        "freshness": {t: insights._latest_day(conn, t) for t in ("daily", "sleep", "readiness")},
    }


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def render(data: dict[str, Any]) -> str:
    b = data["brief"]
    r = b["readiness"]
    g = r["garmin"] or {}
    chips = "".join(f'<span class="chip bad">{_e(x)}</span>' for x in r["ours"]["holding_back"])
    chips += "".join(f'<span class="chip good">{_e(x)}</span>' for x in r["ours"]["helping"])
    vitals = "".join(
        f'<span class="chip {"good" if v["state"] == "in range" else "bad"}">{_e(k)}: '
        f'{_e(v["value"])} ({_e(v["state"])})</span>'
        for k, v in data["ranges"]["metrics"].items())
    feed = "".join(
        f'<li class="lvl{i["level"]}"><b>L{i["level"]} · {_e(i["title"])}</b><br>'
        f'<span>{_e(i["detail"])}</span></li>' for i in data["feed"])
    preds = data["predictions"]["predictions"]
    pred_rows = "".join(
        f"<tr><td>{_e(k)}</td><td>{_e(v.get('effective_vo2max'))}</td>"
        f"<td>{_e(v.get('best_effort_riegel_1.06'))}</td>"
        f"<td class='g'>{_e(v.get('garmin'))}</td></tr>" for k, v in preds.items())
    run_rows = "".join(
        f"<tr><td>{_e(x['date'])}</td><td>{_e(x['km'])}</td><td>{_e(x['pace'])}</td>"
        f"<td>{_e(x['hr'])}</td><td>{_e(x['ef'])}</td><td>{_e(x['decoupling'])}</td>"
        f"<td>{_e(x['cadence'])}</td><td>{_e(x['gct'])}</td><td>{_e(x['vr'])}</td></tr>"
        for x in data["runs"])
    rel = "".join(f"<li>{_e(x['statement'])}</li>" for x in data["relationships"]) or \
        "<li>No relationship passes the evidence bar yet.</li>"
    trends = "".join(f"<tr><td>{_e(k)}</td><td>{_e(v['direction'])}</td>"
                     f"<td>{_e(v['per_30_days'])}</td><td>{_e(v['ci95'])}</td></tr>"
                     for k, v in data["trends"].items())
    wk = data["weekly"]["week"]
    th = data["thresholds"]
    fa = data["fitness_age"] or {}
    form = data["form"] or {}
    swims = "".join(f"<tr><td>{_e(s['date'])}</td><td>{_e(s['distance_m'])}</td>"
                    f"<td>{_e(s['pace_per_100m'])}</td></tr>" for s in data["swims"])
    strength = "".join(f"<tr><td>{_e(s['month'])}</td><td>{_e(s['sessions'])}</td>"
                       f"<td>{_e(s['sets'])}</td><td>{_e(s['reps'])}</td></tr>"
                       for s in data["strength"])
    payload = json.dumps({k: data[k] for k in ("recovery", "hrv", "fitness", "garmin_acute",
                                                "sleep", "rhr", "curve", "calendar")},
                         default=str)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Garmin Health Dashboard</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--muted:#667085;--line:#e4e7ec;--good:#12805c;
--bad:#b42318;--accent:#2563eb;--garmin:#475467}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0f1218;--card:#171b23;
--fg:#e6e8ec;--muted:#98a2b3;--line:#2a303b;--good:#32d583;--bad:#f97066;--accent:#60a5fa;
--garmin:#98a2b3}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.45 -apple-system,system-ui,Segoe UI,Roboto,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:16px}}h1{{font-size:22px;margin:4px 0}}
h2{{font-size:16px;margin:0 0 8px}}.muted{{color:var(--muted);font-size:13px}}
.grid{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;
overflow-x:auto}}.big{{font-size:28px;font-weight:700}}.chip{{display:inline-block;border-radius:99px;
padding:2px 10px;margin:2px;font-size:12px;border:1px solid var(--line)}}
.good{{color:var(--good)}}.bad{{color:var(--bad)}}.g::before{{content:"G ";font-weight:700;
color:var(--garmin);font-size:11px;border:1px solid var(--garmin);border-radius:4px;padding:0 3px;
margin-right:4px}}table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}
ul.feed{{list-style:none;padding:0;margin:0}}ul.feed li{{padding:8px 0;border-bottom:1px solid
var(--line)}}.lvl2 b{{color:var(--accent)}}.lvl3 b{{color:var(--good)}}canvas{{max-height:260px}}
.cal{{display:grid;grid-template-columns:repeat(26,1fr);gap:2px}}.cal div{{aspect-ratio:1;
border-radius:2px;background:var(--line)}}footer{{margin:20px 0;color:var(--muted);font-size:12px}}
</style></head><body><main>
<h1>Garmin Health Dashboard</h1>
<div class="muted">Data through {_e(data['end'])} · sleep {_e(data['freshness']['sleep'])} ·
<span class="g">Garmin's own value</span> vs unmarked = computed here (METRICS.md)</div>
<div class="grid" style="margin-top:12px">
 <div class="card"><h2>Today</h2><div class="big">{_e(r['ours']['state'])}</div>
  <div>Our readiness z = {_e(r['ours']['composite_z'])} ·
  <span class="g">readiness {_e(g.get('score'))} {_e(g.get('level'))}</span></div>
  <p><b>{_e(b['suggestion']['suggest'])}</b><br><span class="muted">
  {_e(b['suggestion']['why'])}</span></p>{chips}</div>
 <div class="card"><h2>Vitals vs your range</h2>{vitals}
  <p class="muted">{_e(data['ranges']['meaning'])}</p></div>
 <div class="card"><h2>Fitness & form</h2>
  <div>CTL {_e(form.get('ctl'))} · ATL {_e(form.get('atl'))} · {_e(form.get('zone'))}</div>
  <div class="muted">HRmax {_e(th['hr_max'])} · LTHR {_e(th['lthr'])} · rest {_e(th['hr_rest'])}
  · <span class="g">HRmax setting {_e(th['garmin']['hr_max_setting'])}</span></div>
  <div style="margin-top:6px"><span class="g">fitness age {_e(fa.get('garmin_fitness_age'))}
  (age {_e(fa.get('chronological_age'))})</span></div></div>
</div>
<div class="card" style="margin-top:12px"><h2>Insights</h2><ul class="feed">{feed}</ul></div>
<div class="grid" style="margin-top:12px">
 <div class="card"><h2>HRV and normal band (60 d)</h2><canvas id="hrv"></canvas></div>
 <div class="card"><h2>Fitness / fatigue / form (90 d)</h2><canvas id="pmc"></canvas></div>
 <div class="card"><h2>Sleep hours and score (60 d)</h2><canvas id="sleep"></canvas></div>
 <div class="card"><h2>Resting heart rate (60 d)</h2><canvas id="rhr"></canvas></div>
</div>
<div class="grid" style="margin-top:12px">
 <div class="card"><h2>Race predictions</h2><table><tr><th></th><th>effective VO2max</th>
  <th>best effort</th><th class="g">Garmin</th></tr>{pred_rows}</table>
  <p class="muted">{_e(data['predictions'].get('volume_warning', ''))}</p></div>
 <div class="card"><h2>Pace curve (best per duration, 1 yr)</h2><canvas id="curve"></canvas></div>
</div>
<div class="card" style="margin-top:12px"><h2>Recent runs</h2><table><tr><th>date</th><th>km</th>
<th>pace</th><th>HR</th><th>EF</th><th>decoupling %</th><th>cadence</th><th>GCT ms</th>
<th>VR %</th></tr>{run_rows}</table></div>
<div class="grid" style="margin-top:12px">
 <div class="card"><h2>This week</h2><div>{_e(wk['sessions'])} sessions · {_e(wk['hours'])} h ·
  {_e(wk['run_km'])} run km · TRIMP {_e(wk['trimp'])}</div>
  <div class="muted">intensity Z1/Z2/Z3 % {_e(wk['intensity_pct'])}</div></div>
 <div class="card"><h2>90-day trends</h2><table><tr><th>metric</th><th>direction</th>
  <th>/30 d</th><th>95% CI</th></tr>{trends}</table></div>
 <div class="card"><h2>Patterns in your data</h2><ul>{rel}</ul></div>
</div>
<div class="grid" style="margin-top:12px">
 <div class="card"><h2>Training load, last 26 weeks</h2><div class="cal" id="cal"></div>
  <p class="muted">darker = higher daily TRIMP</p></div>
 <div class="card"><h2>Swims</h2><table><tr><th>date</th><th>m</th><th>/100 m</th></tr>{swims}
  </table></div>
 <div class="card"><h2>Strength</h2><table><tr><th>month</th><th>sessions</th><th>sets</th>
  <th>reps</th></tr>{strength}</table></div>
</div>
<footer>Sources: local database (Garmin Personal API &gt; unofficial Garmin Connect &gt; Garmin
export). Associations are not causes. Generated by garmin-mcp.</footer>
</main>
<script src="{CHART_JS}"></script>
<script>
const D={payload};
const css=getComputedStyle(document.documentElement);
const C=n=>css.getPropertyValue(n).trim();
function line(id,labels,sets){{new Chart(document.getElementById(id),{{type:'line',
 data:{{labels,datasets:sets}},options:{{responsive:true,maintainAspectRatio:false,
 plugins:{{legend:{{labels:{{color:C('--fg')}}}}}},elements:{{point:{{radius:0}}}},
 scales:{{x:{{ticks:{{color:C('--muted'),maxTicksLimit:6}}}},y:{{ticks:{{color:C('--muted')}}}}}}}}}});}}
if(window.Chart){{
 const rd=D.recovery;
 line('hrv',rd.map(x=>x.day.slice(5)),[
  {{label:'7-day HRV (ms)',data:rd.map(x=>x.hrv_7d_ms),borderColor:C('--accent')}},
  {{label:'band low',data:rd.map(x=>x.hrv_band_ms?x.hrv_band_ms[0]:null),borderColor:C('--muted'),borderDash:[4,4]}},
  {{label:'band high',data:rd.map(x=>x.hrv_band_ms?x.hrv_band_ms[1]:null),borderColor:C('--muted'),borderDash:[4,4]}}]);
 const f=D.fitness;
 line('pmc',f.map(x=>x.day.slice(5)),[
  {{label:'CTL fitness',data:f.map(x=>x.ctl),borderColor:C('--accent')}},
  {{label:'ATL fatigue',data:f.map(x=>x.atl),borderColor:C('--bad')}},
  {{label:'TSB form',data:f.map(x=>x.tsb),borderColor:C('--good')}},
  {{label:'G acute load /10',data:f.map(x=>D.garmin_acute[x.day]!=null?D.garmin_acute[x.day]/10:null),borderColor:C('--garmin'),borderDash:[2,3]}}]);
 const s=D.sleep;
 line('sleep',s.map(x=>x.day.slice(5)),[
  {{label:'hours',data:s.map(x=>x.h),borderColor:C('--accent')}},
  {{label:'G score /10',data:s.map(x=>x.score!=null?x.score/10:null),borderColor:C('--garmin'),borderDash:[2,3]}}]);
 line('rhr',D.rhr.map(x=>x.day.slice(5)),[{{label:'resting HR',data:D.rhr.map(x=>x.rhr),borderColor:C('--bad')}}]);
 new Chart(document.getElementById('curve'),{{type:'bar',data:{{labels:D.curve.map(x=>(x.window_s/60)+' min'),
  datasets:[{{label:'pace (min/km, lower = faster)',data:D.curve.map(x=>x.window_s/x.distance_m*1000/60),backgroundColor:C('--accent')}}]}},
  options:{{plugins:{{legend:{{labels:{{color:C('--fg')}}}}}},scales:{{x:{{ticks:{{color:C('--muted')}}}},y:{{ticks:{{color:C('--muted')}}}}}}}}}});
}}
const cal=document.getElementById('cal');const days=Object.entries(D.calendar).slice(-182);
const mx=Math.max(1,...days.map(([d,v])=>v.trimp||0));
for(const [d,v] of days){{const el=document.createElement('div');const t=(v.trimp||0)/mx;
 el.title=d+' TRIMP '+(v.trimp||0);el.style.background=t?`color-mix(in srgb, ${{C('--accent')}} ${{Math.round(20+80*t)}}%, transparent)`:'';
 cal.appendChild(el);}}
</script></body></html>"""


def build(conn: sqlite3.Connection, out_dir: Path | None = None) -> Path:
    from garmin_mcp.config import data_dir

    out_dir = out_dir or data_dir() / "dashboard"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(render(collect(conn)), encoding="utf-8")
    return path


def main() -> None:
    from garmin_mcp import db
    from garmin_mcp.config import db_path

    print(build(db.connect(db_path())))


if __name__ == "__main__":
    main()
