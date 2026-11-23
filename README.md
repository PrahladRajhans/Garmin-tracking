# Garmin-tracking

A free, self-hosted [MCP](https://modelcontextprotocol.io) server that connects your Garmin Connect
account to AI assistants (Claude Desktop, Claude Code, etc.), so you can ask questions about your
health and training data without a paid connector.

> **Status:** early scaffold (v0.1.0). Read-only, 4 tools. See [CHANGELOG.md](CHANGELOG.md).
> **Plan:** see [ROADMAP.md](ROADMAP.md) for decisions and phased build order.

## How it works

```
AI assistant  <--MCP (stdio)-->  garmin-mcp (this repo)  <--HTTPS-->  Garmin Connect
```

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

`day` is `YYYY-MM-DD` and defaults to today.

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/PrahladRajhans/Garmin-tracking.git
cd Garmin-tracking
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# One-time login (supports MFA). Saves tokens to ~/.garminconnect
python -m garmin_mcp.login
```

After this, the server reuses the saved tokens; your password is not stored.

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
tests/
```

Every change must add an entry to [CHANGELOG.md](CHANGELOG.md) and keep this README in sync.

## License

MIT
