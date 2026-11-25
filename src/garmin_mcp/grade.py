"""Distance-window grade estimates for time-ordered FIT activity samples."""

from bisect import bisect_left
from collections.abc import Iterable
from math import isfinite

MAX_SAMPLE_GAP_S = 10
WINDOW_M = 20.0

Sample = tuple[float | None, float | None, float | None]  # elapsed/absolute time, distance, altitude


def interval_grades(samples: Iterable[Sample]) -> list[float | None]:
    """Return one grade per adjacent pair, with None when grade cannot be estimated."""
    points = list(samples)
    grades = [None] * max(0, len(points) - 1)
    start = 0
    for end in range(1, len(points)):
        ta, da, za = points[end - 1]
        tb, db, zb = points[end]
        if (ta is None or tb is None or not 0 < tb - ta <= MAX_SAMPLE_GAP_S
                or not all(isinstance(value, (int, float)) and isfinite(value) for value in (da, db, za, zb))
                or da < 0 or db <= da):
            _fill_grades(grades, points, start, end)
            start = end
    _fill_grades(grades, points, start, len(points))
    return grades


def _fill_grades(grades: list[float | None], points: list[Sample], start: int, end: int) -> None:
    if end - start < 2 or points[end - 1][1] - points[start][1] < WINDOW_M:
        return
    distances = [distance for _, distance, _ in points[start:end]]
    altitudes = [altitude for _, _, altitude in points[start:end]]

    def altitude_at(distance: float) -> float:
        i = bisect_left(distances, distance)
        if i == 0 or distances[i] == distance:
            return altitudes[i]
        fraction = (distance - distances[i - 1]) / (distances[i] - distances[i - 1])
        return altitudes[i - 1] + fraction * (altitudes[i] - altitudes[i - 1])

    for i in range(len(distances) - 1):
        centre = (distances[i] + distances[i + 1]) / 2
        left = min(max(centre - WINDOW_M / 2, distances[0]), distances[-1] - WINDOW_M)
        right = min(left + WINDOW_M, distances[-1])
        # Round far below sensor resolution so exact slope-bin edges agree between recording rates.
        grades[start + i] = round((altitude_at(right) - altitude_at(left)) / WINDOW_M, 6)
