"""Compare recorded kilometre splits on conservatively matched GPS traces."""

from bisect import bisect_left
from datetime import UTC, datetime
from math import cos, hypot, isfinite, radians


def _trace(conn, activity_id):
    trace = []
    for distance, lat, lon, stamp in conn.execute(
            "SELECT distance,lat,lon,ts FROM fit_records WHERE activity_id=? ORDER BY ts",
            (activity_id,)):
        if not all(isinstance(v, (int, float)) and isfinite(v) for v in (distance, lat, lon)):
            continue
        if not -90 <= lat <= 90 or not -180 <= lon <= 180 or distance < 0 or (lat == lon == 0):
            continue
        try:
            t = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            continue
        t = (t if t.tzinfo else t.replace(tzinfo=UTC)).timestamp()
        if not trace or (distance > trace[-1][0] and t > trace[-1][3]):
            trace.append((distance, lat, lon, t))
    return trace


def _samples(trace, distances):
    path = [point[0] for point in trace]
    result = []
    for distance in distances:
        i = bisect_left(path, distance)
        if i < len(path) and path[i] == distance:
            result.append(trace[i][1:])
            continue
        if i == 0 or i == len(path) or path[i] - path[i - 1] > 100:
            return []
        ratio = (distance - path[i - 1]) / (path[i] - path[i - 1])
        result.append(tuple(a + ratio * (b - a) for a, b in zip(trace[i - 1][1:], trace[i][1:], strict=True)))
    return result


def match(trace, earlier):
    if not trace or not earlier or max(trace[0][0], earlier[0][0]) > 50:
        return []
    end = min(trace[-1][0], earlier[-1][0])
    if end < 2000 or abs(trace[-1][0] - earlier[-1][0]) > end * .03:
        return []
    # Use an equal recorded distance in both traces. Start after any first-fix offset.
    checkpoints = range(50, int(end) + 1, 250)
    current, prior = _samples(trace, checkpoints), _samples(earlier, checkpoints)
    if not current or not prior:
        return []
    for (a, b, _), (c, d, _) in zip(current, prior, strict=True):
        if 111_195 * hypot(a - c, (b - d) * cos(radians((a + c) / 2))) > 55:
            return []
    rows = []
    for j in range(4, len(current), 4):
        this_seconds = round(current[j][2] - current[j - 4][2])
        prior_seconds = round(prior[j][2] - prior[j - 4][2])
        rows.append({"from_m": checkpoints[j - 4], "to_m": checkpoints[j],
                     "elapsed": this_seconds, "prior_elapsed": prior_seconds,
                     "difference": this_seconds - prior_seconds})
    return rows


def compare(conn, run):
    activity_id = run["activity_id"]
    c = run.get("comparable_effort", {})
    if not c.get("matches"):
        return None
    trace = _trace(conn, activity_id)
    for candidate in c["matches"]:
        other = candidate["activity_id"]
        if rows := match(trace, _trace(conn, other)):
            return {"activity_id": other, "date": candidate["start_local"][:10], "rows": rows}
    return None
