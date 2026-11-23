# Mac setup (one time)

Open the Claude desktop app → **Code** → start a **Local** session in the folder
`~/Garmin-tracking`, and send it this message:

> Follow MAC_SETUP.md in this repo, section "Steps for Claude". Run each command yourself,
> fix any problem you hit, and tell me only what needs my decision.

---

## Steps for Claude

Run from `~/Garmin-tracking`. Python 3.12+ is installed (`python3 --version`; the user has 3.15).

1. **Update code and environment**
   ```bash
   git fetch origin && git checkout claude/affectionate-thompson-ko3x70 && git pull
   [ -d .venv ] || python3 -m venv .venv
   .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -e '.[dev]'
   .venv/bin/pytest -q
   ```
2. **Check credentials exist** (never print their contents):
   `test -s ~/.config/garmin/connect-personal-api-key && echo key-ok` and
   `ls ~/.garminconnect/` (unofficial login tokens). If the key is missing, ask the user to
   save it with the hidden-prompt method in README. If the unofficial tokens are missing, ask
   the user to run `.venv/bin/python -m garmin_mcp.login` (it needs their password/MFA).
3. **Import full history** from the Garmin export in Downloads:
   `ls ~/Downloads | grep -i garmin`, then
   `.venv/bin/garmin-mcp-import "<that zip or folder>"`.
4. **Backfill a year from the APIs** (adds unofficial extras: readiness factors, training
   status etc. for recent months; the official API is rate-limited to ~100 requests/window and
   the sync waits automatically; expect 30–60 min):
   `.venv/bin/garmin-mcp-sync --days 365 > ~/.garmin-mcp/backfill.log 2>&1` (run in background
   and check `--coverage` when done).
5. **Connect to Claude Desktop**: add to
   `~/Library/Application Support/Claude/claude_desktop_config.json` (merge, don't overwrite
   other servers):
   ```json
   {"mcpServers": {"garmin": {"command": "/Users/<user>/Garmin-tracking/.venv/bin/garmin-mcp"}}}
   ```
   Tell the user to restart the Claude desktop app.
6. **Schedule sync every 3 hours** with a launchd agent
   `~/Library/LaunchAgents/com.garmin-mcp.sync.plist` running
   `/Users/<user>/Garmin-tracking/.venv/bin/garmin-mcp-sync --days 3`, StartInterval 10800,
   stdout/stderr to `~/.garmin-mcp/sync.log`; then `launchctl load` it.
7. **Updates later**: `git pull && .venv/bin/pip install -e .`, then restart the Claude
   desktop app. The dashboard is at `~/.garmin-mcp/dashboard/index.html` (rebuilt after each
   sync; `open` it).
8. **Verify**: `.venv/bin/garmin-mcp-sync --coverage`, and in Claude Desktop ask
   "show my health snapshot". Report results to the user.
