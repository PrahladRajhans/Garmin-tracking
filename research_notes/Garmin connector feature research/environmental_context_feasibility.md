# Weather and air quality feasibility, November 2026

The useful first question is whether an outdoor workout was unusual for its conditions.
A future trial could show timed observations alongside pace, grade and heart rate.
The sources support a descriptive layer. Personal weather-adjusted performance scores,
hydration inferences and sleep coaching need stronger evidence. This note proposes
no data collection, provider integration, release date or model change.

## Evidence and limits

| Question | Published finding | Implication for Garmin-tracking |
|---|---|---|
| Heat, moisture and outdoor exercise | The [2015 heat consensus](https://pmc.ncbi.nlm.nih.gov/articles/PMC4602249/) describes increased physiological strain and impaired endurance capacity in heat. Air temperature, humidity, radiant load and wind affect heat exchange. [Ely et al.](https://doi.org/10.1249/mss.0b013e31802d3aba) studied weather and marathon performance. | Show temperature, dew point or humidity, wind, and observed precipitation with the time and source. Terrain, effort, acclimation, fluid intake, stops and sensor quality can all explain an individual's heart-rate drift. A wrist temperature reading has a different meaning from ambient air temperature. |
| Pollution and workout response | The [2021 evidence mapping review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7816214/) covers exposure during activity and evidence on health interactions. Results vary by pollutant, population, design and outcome. | Annotate available concentrations or reported AQI and its standard. A city monitor or model cell cannot establish the runner's dose, breathing symptoms or the cause of a heart-rate change. |
| Temperature and sleep | The [thermal environment review](https://pmc.ncbi.nlm.nih.gov/articles/PMC3427038/) treats clothing, bedding and the bed microclimate as relevant. [Minor et al.](https://doi.org/10.1016/j.oneear.2022.04.008) studied the association of outdoor nighttime temperature with wearable-derived sleep globally. | Overnight outdoor conditions are regional context. Bedroom temperature, humidity, ventilation and indoor exposure require separate observations. Travel, AC, bedding, and sleep schedules can change the result. Defer sleep advice pending input-quality checks. |

## Source candidates and validation

| Source | Role | What was verified and what remains |
|---|---|---|
| [Garmin saved activity weather](../../src/garmin_mcp/insights.py) and [stored FIT data](../../src/garmin_mcp/fit.py) | Compare the existing session context with the local timed track and watch temperature. | Code already reads saved weather when present. Sample completeness, underlying station/time and FIT sensor setup require owner-archive inspection. Garmin and a second provider may rely on the same stations. |
| [NOAA Global Hourly (ISD)](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database), [station inventory](https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv), IMD local observations | Prefer quality-flagged station observations near the applicable time, elevation and route. | The NOAA inventory returned Chandigarh candidates 421050 and 427052 whose listed records end in 2025. Current coverage needs confirmation. The IMD site could not be verified in this session. Distance to the run alone cannot establish representativeness. |
| [Copernicus ERA5](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview), [Open-Meteo source and service terms](https://github.com/open-meteo/open-meteo#readme) | Fill historical weather gaps and compare with station observations. | ERA5 documents hourly single-level fields at 0.25° resolution for the regridded reanalysis. Open-Meteo's repository documents a historical API and non-commercial access. The live endpoint documentation was blocked here, so field definitions, history, model options and service capacity still need direct verification. ERA5 fetched through two interfaces is one underlying source. |
| [CPCB national AQI](https://cpcb.nic.in/National-Air-Quality-Index/), [OpenAQ measurements](https://docs.openaq.org/resources/measurements) | Prefer locally reported AQI and quality-flagged pollutant readings. | OpenAQ documents per-sensor measurements and precomputed hourly data. Coverage, licensing, station siting, reporting lag and completeness need a local audit. CPCB and India OGD pages were inaccessible in this session. Confirm the official India AQI categories, averaging windows and coverage rules before deriving or displaying a custom index. |
| [CAMS global reanalysis](https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4?tab=overview) | Regional historical pollution context where stations are missing. | Dataset catalog and particulate variables were available. Grid/time resolution and delivery lag need to be checked for each product and variable. A regional modeled estimate should have its own label, with local observations kept distinct. |

## A trial worth considering later

1. **Review coverage first.** With consent, use only coarse approved cells or representative
   waypoints and UTC time buckets. Keep the full route, precise home and sleep locations,
   watch serial, and activity IDs local. Start with outdoor activities with a usable clock and
   location. Avoid IP geolocation, inferring sleep location from runs, or fetching weather when
   someone opens the dashboard. Cache and timestamp values and support deleting them.
2. **Triangulate rather than average.** Record observation vs model, provider and underlying
   product, interval, unit, station or grid resolution, elevation, retrieval date, and quality.
   Join the activity's actual time range in UTC. Keep temperature in °C, relative humidity
   in percent, wind in m/s, and precipitation accumulation in mm with its interval. Distinguish a
   measured zero from missing data. Preserve pollutant and averaging window. Display local
   India AQI only with a verified standard and window. Instant concentration, forecast AQI
   and a rolling or daily AQI describe different things.
3. **Check on held-out public stations and historical workouts.** Compare observed weather and
   models at matching time, elevation and location. Log coverage, error, disagreement across
   hot or wet days and large gaps. Share ranges when sources disagree. Use a separate indoor
   logger or explicit indoor records before treating environmental data as sleep exposure.
4. **Validate whether the layer improves interpretation.** Compare similar outdoor routes,
   pace ranges, gradients, durations and effort under different conditions. Hold out later
   weeks. Examine season, recent load, sleep, time of day, altitude, wind, sensor quality,
   acclimation, fueling and indoor/outdoor selection. Temperature and humidity move together,
   and rain can change the route or which days get recorded. Test a small set of prespecified
   outcomes such as HR at comparable pace and HR drift. Show sample size, uncertainty and
   missingness. A weather correction belongs in coaching only if it replicates and adds
   useful information beyond the existing matched-run baseline.
