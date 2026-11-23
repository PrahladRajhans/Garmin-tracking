# Garmin-tracking

A free, self-hosted [MCP](https://modelcontextprotocol.io) server that connects your Garmin Connect
account to AI assistants (Claude Desktop, Claude Code, etc.), so you can ask questions about your
health and training data without a paid connector.

> **Status:** v0.2.0, Phase 1 (data foundation). Local SQLite sync of all FR955 data. See [CHANGELOG.md](CHANGELOG.md).
> **Metric design:** [METRICS.md](METRICS.md) explains how each derived metric is calculated (Garmin vs science vs ours).
> **Plan:** see [ROADMAP.md](ROADMAP.md) for decisions and phased build order.

## How it works

```
Garmin Connect --(scheduled sync)--> local SQLite (~/.garmin-mcp) <--reads-- MCP server <--> AI assistant
```

The sync job stores every Garmin response verbatim plus parsed FIT streams, so the assistant reads
fast local data and Garmin is called only by the scheduled sync (or the `refresh_data` tool).

It uses the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
Python library, which talks to the same endpoints as the Garmin Connect website.

**Caveat:** this is *not* the official Garmin Health API (that requires a business partnership).
Garmin can change or block these endpoints at any time, which would break the server until the
library is updated. Use your own account only.

## Tools

| Tool | What it returns |
|------|-----------------|
| `get_daily_summary(day?)` | Steps, calories, resting HR, stress, body battery for a day |
| `get_sleep(day?)` | Sleep stages, score, timings |
| `get_heart_rate(day?)` | Heart-rate timeline and resting HR |
| `get_recent_activities(limit=10)` | Latest activities, newest first (max 100) |
| `refresh_data(days=3)` | Sync recent days from Garmin into the local database |
| `data_coverage()` | What is stored locally, date ranges, last sync and errors |

The first four tools still call Garmin live; Phase 2 moves them onto the local database.

`day` is `YYYY-MM-DD` and defaults to today.

## Setup

Requires Python 3.12+.

```bash
git clone https://github.com/PrahladRajhans/Garmin-tracking.git
cd Garmin-tracking
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 1) Official Personal API key (primary source). Create it at
#    https://connect.garmin.com/app/settings/personalApiToken, then save it to a private file:
mkdir -p ~/.config/garmin && chmod 700 ~/.config/garmin
printf '%s' 'PASTE_YOUR_KEY' > ~/.config/garmin/connect-personal-api-key
chmod 600 ~/.config/garmin/connect-personal-api-key

# 2) Unofficial login (adds training readiness/status, race predictor, endurance/hill score,
#    lactate threshold, acclimation). One-time, supports MFA. Saves tokens to ~/.garminconnect
python -m garmin_mcp.login
```

Never commit the key or paste it into chats or issues. The key file location is the same one
Garmin's official client (`garmin-connect-personal-api-python`) reads; `GARMIN_PERSONAL_API_KEY`
also works. Keys expire (30 days to 1 year), so set a reminder to renew yours.

**Sources:** `--source both` (default) syncs the official API first, then only the extras from the
unofficial library. If either is unavailable it is reported and skipped; the other still syncs.
Use `--source personal_api` for official-only.

After this, the server reuses the saved tokens; your password is not stored.

### Import your full history (one time)

Request your data at Garmin (Account → Data Management → Export Your Data), download the ZIP, then:

```bash
garmin-mcp-import ~/Downloads/<your-export>.zip     # or the unzipped folder
```

It loads everything since you started using Garmin: activities with original FIT files, daily
summaries, sleep, health status (overnight HRV/RHR/SpO2/respiration vs baseline), training
readiness, training status, race predictions, endurance/hill score, acute load, VO2max,
acclimation, hydration, personal records, zones. Safe to re-run; activities already synced from
the API are never overwritten.

### Sync your data

```bash
garmin-mcp-sync --days 365     # first run: backfill a year (takes a while, ~25 calls/day)
garmin-mcp-sync                # later runs: last 7 days, only new/changed data is fetched
garmin-mcp-sync --coverage     # show what is stored
```

What gets synced (official Personal API):
- **Daily:** daily summary, sleep, HRV, all-day heart rate, SpO2, fitness age.
- **Windowed (28-day chunks, the API's history cap):** Body Battery, stress, steps, hydration, VO2max, weight, HRV and sleep summaries.
- **Per activity:** summary + original FIT file.

Extras from the unofficial library: training readiness, training status, VO2max/max metrics, respiration, intensity minutes, Body Battery events, heat/altitude acclimation, floors, race predictions, endurance score, hill score, lactate threshold, body composition, plus activity splits, HR/power zones and weather.

In `--source garminconnect` mode (unofficial only):
- **Daily:** summary, sleep, HRV, training readiness, training status, stress/Body Battery, all-day HR, respiration, SpO2, VO2max/max metrics, fitness age, intensity minutes, hydration, Body Battery events, heat/altitude acclimation, floors.
- **Windowed:** race predictions, endurance score, hill score, lactate threshold, body composition, weigh-ins.
- **Per activity:** summary, splits, HR/power zones, weather, original FIT file (1 s records, laps, beat-to-beat HRV) saved in `~/.garmin-mcp/fit/`.

Already-stored days are skipped except the last 2, which Garmin keeps updating. A failing endpoint is logged and skipped; the run stops early after 8 failures in a row (usually expired login).

**Schedule it** (every 3 hours), for example on macOS/Linux with `crontab -e`:

```
0 */3 * * * /absolute/path/to/Garmin-tracking/.venv/bin/garmin-mcp-sync >> ~/.garmin-mcp/sync.log 2>&1
```

On Windows, use Task Scheduler to run `garmin-mcp-sync.exe` from `.venv\Scripts`.

### Connect to Claude Desktop

Add to `claude_desktop_config.json` (use the absolute path to your venv):

```json
{
  "mcpServers": {
    "garmin": {
      "command": "/absolute/path/to/Garmin-tracking/.venv/bin/garmin-mcp"
    }
  }
}
```

### Connect to Claude Code

```bash
claude mcp add garmin -- /absolute/path/to/Garmin-tracking/.venv/bin/garmin-mcp
```

## Configuration

Optional environment variables (or a `.env` file, see `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `GARMIN_TOKEN_DIR` | `~/.garminconnect` | Where session tokens are stored |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | unset | Fallback login if no tokens exist (prefer the login script) |
| `GARMIN_DATA_DIR` | `~/.garmin-mcp` | Database and FIT files |
| `GARMIN_DB_PATH` | `$GARMIN_DATA_DIR/garmin.db` | SQLite file |

## Development

```bash
pip install -e '.[dev]'
pytest
ruff check .
```

Project layout:

```
src/garmin_mcp/
  server.py   # MCP tool definitions
  client.py   # Garmin auth + helpers
  login.py    # one-time interactive login
  config.py   # data paths
  db.py       # SQLite schema + storage helpers
  fit.py      # FIT parsing (official garmin-fit-sdk)
  sync.py     # incremental sync engine + CLI
  sources/    # garminconnect (unofficial), personal_api (pending key)
tests/
```

Every change must add an entry to [CHANGELOG.md](CHANGELOG.md) and keep this README in sync.

## License

MIT
