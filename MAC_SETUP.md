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
   git fetch origin && git checkout main && git pull --ff-only
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
6. **Schedule sync every 3 hours** (since v0.12 each run first checks a gate: full sync only if ≥ 11 h since the last one or a new activity exists, otherwise one cheap call) with a launchd agent
   `~/Library/LaunchAgents/com.garmin-mcp.sync.plist` running
   `/Users/<user>/Garmin-tracking/.venv/bin/garmin-mcp-sync --days 3`, StartInterval 10800,
   stdout/stderr to `~/.garmin-mcp/sync.log`; then `launchctl load` it.
7. **Updates later**: `git pull && .venv/bin/pip install -e .`, then restart the Claude
   desktop app. The dashboard is at `~/.garmin-mcp/dashboard/index.html` (rebuilt after each
   sync; `open` it).
8. **Verify**: `.venv/bin/garmin-mcp-sync --coverage`, and in Claude Desktop ask
   "show my health snapshot". Report results to the user.

## Private phone access (optional)

This part is new in v0.13.1. It is implemented and tested with stand-ins, but **not yet deployed
or verified on this Mac/phone**. Leave publishing disabled until the account checks succeed.
The default local dashboard, sync schedule, and analytics work without Cloudflare or Node.

### One-time actions for the owner

1. Create a Cloudflare account and select the free Pages and Zero Trust plans. Confirm the
   current Access allowance in the account UI before activating hosting. Cloudflare setup
   docs confirm a Zero Trust Free plan. The published plan content we retrieved did not
   specify the current Access seat allowance. No paid domain is required.
2. With the local assistant, create a **dedicated Direct Upload** Pages project and deploy
   only an empty, non-health placeholder. In Pages settings enable Access for previews, then
   follow [Cloudflare's production-domain instructions](https://developers.cloudflare.com/pages/platform/known-issues/#enable-access-on-your-pagesdev-domain).
   The result must be two self-hosted Access apps: `PROJECT.pages.dev` and `*.PROJECT.pages.dev`
   (use the actual Pages subdomain if Cloudflare added a suffix). Each must have one Allow policy
   whose Include rule is **Emails → your exact email**. Enable the One-time PIN identity provider.
   Do not add custom domains, path-specific apps, bypass rules, or public destination overrides.
3. Create an API token scoped to this account with **Cloudflare Pages Edit** and
   **Access: Apps and Policies Read**. Save it securely with the local assistant in the ignored
   repo `.env`; never paste its value into chat or commit it. The assistant can fill the
   non-secret settings from the account; no further Garmin login or backfill is needed.

Then ask your local assistant to follow the remaining section. These are instructions for
the assistant to execute, rather than a terminal sequence the owner needs to copy.

### Steps for the local assistant

- Preserve existing `.env` values and launchd settings. Check variable names/presence only;
  never print secrets. Confirm Node supports Wrangler (tested here with Node 24.22.3).
- Install the tested CLI outside the repo:
  `npm install --prefix ~/.garmin-mcp/cloudflare wrangler@4.166.0`.
- Fill the six publishing settings in `.env` using `.env.example` as a key list:
  `GARMIN_DASHBOARD_PUBLISH=cloudflare`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
  `GARMIN_CLOUDFLARE_PROJECT`, `GARMIN_DASHBOARD_EMAIL`, and the absolute `GARMIN_WRANGLER` path.
  Restrict the file to its owner (`chmod 600 .env`). Ensure the scheduled process's PATH contains
  Node: Wrangler uses `/usr/bin/env node`, and launchd does not inherit the interactive shell PATH.
- Run `.venv/bin/python -m garmin_mcp.publish --check`. This reads account configuration,
  checks all Access apps for overlapping project paths, and checks anonymous production and
  wildcard-host requests. It uploads nothing and returns `status: checked` only when successful.
  If a fresh project needs an initial deployment for routing, use a non-health placeholder.
- Only after that succeeds, run `.venv/bin/garmin-mcp-dashboard`. Check its publishing result,
  then open the production URL on the phone: private browsing must require login, a different
  email must be denied, and the owner's One-time PIN must open the dashboard. Test every page
  link and a run link. Check a direct deployment URL also requires login.
- Check the next scheduled sync publishes an update. A dashboard build retains its local and
  iCloud copies even when uploading is refused or fails. Keep the Access apps in place for
  **all existing deployments**; disabling publishing does not remove cloud copies.

Hosting rationale and sources: [private_dashboard_hosting.md](research_notes/Garmin%20connector%20feature%20research/private_dashboard_hosting.md).

### Archive timing comparison

After the normal Mac update has installed v0.14.3, run one command from the repo:
`.venv/bin/garmin-mcp-verify --run-timing`. It compares paired run timings and heart rate
with the stored Garmin summaries by year. It opens SQLite read-only and prints only group
counts and aggregate differences. Keep the report local unless you choose to share it.
Investigate large residuals alongside a few corresponding Garmin Connect activities.

### Open the interactive dashboard

In Safari on the Mac, open the local generated HTML and tap **Light** or **Dark**.
The small offline script also enables selecting values directly on charts. On iPhone
the Files preview may show the static charts only. Check whether the theme switch
appears to confirm the reader runs the controls. An Access-protected website in Safari
is the alternative when Files does not support the interactions.

The history panel includes up to 12 completed months plus the current month. A private
hosted upload would include the same recorded day summaries and recent workout traces
shown locally. Verify Access and consent before publishing a real archive snapshot.

### Check the matched-run release locally

After the scheduled update, ask the local Claude assistant to open the latest private
dashboard and inspect **Running → a run → Heart rate on similar runs** and **Training**.
Have it compare selected run summaries against Garmin Connect and run the read-only
archive timing command above. If the iCloud folder is missing, the local assistant can
run `open ~/.garmin-mcp/dashboard/index.html` and check whether iCloud Drive is enabled
for the same macOS account running sync. For optional local weather/AQI import, follow
the CSV requirements in README. No environmental account is needed.
