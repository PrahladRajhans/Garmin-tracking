# Preview a running workout

Call the `create_workout` MCP tool with `upload=false` to review a proposed workout offline.
It uses the local archive to check heart-rate limits when a usable maximum is available, then
builds the existing Garmin Connect JSON and shows the same steps as a structured preview.

The preview lists step order and repeat nesting, duration in seconds or distance in metres,
and pace as min/km, heart rate as bpm, or the requested zone number. Use the ordered rows to
check that a progression actually gets faster and that every recovery sits in the intended repeat.
Repeat groups count once as encoded steps. Every in-group step is included in performed-step totals.
The local compiler accepts 1–30 iterations for each repeat. This is an app validation setting.

`fixed_time_s` adds time-based steps and `fixed_distance_m` adds distance-based steps. Both
respect repeat counts. When all distance steps have pace targets, `time_at_target_range_s`
adds the time at each end of those targets to the programmed fixed time. It is a planning
estimate. If any distance lacks a pace target, the preview shows that distance and leaves
the time range unavailable. The separate Garmin JSON estimate uses 2.8 m/s for all distance steps.

Garmin describes transferring custom workouts to the Forerunner 955. The offline preview
confirms that the local compiler can represent the selected steps. It has no live confirmation
from Garmin Connect or the paired watch, particularly for nested repeats and running zone
settings. A preview date is only the requested schedule. Upload and scheduling still require
an explicitly requested `upload=true` call. [Garmin Forerunner 955 workout transfer](https://www8.garmin.com/manuals/webhelp/GUID-9D99A9D4-467A-4F1A-A0EA-023184FEA3DD/EN-US/GUID-D6E80F0C-F319-47D1-AF95-0884F3386635.html)

The repeat and pace tests use original synthetic specs and a fake client. The design draws
on the ecosystem review’s structured step parser and fixture-based conversion checks.
[Ecosystem follow-up decisions](GARMIN_ECOSYSTEM_REVIEW.md#follow-up-implementation-decisions)
