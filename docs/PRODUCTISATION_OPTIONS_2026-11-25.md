# Turning this into a multi-user app: open discussion

**Status: parked. An open point of discussion for later. Nothing here is decided or built.**
Written 25 Nov 2026 by Claude at the owner's request, against `main` at v0.33.x. The owner's
direction is to **pursue this only after the nearer-term fixes are done** (the quick fixes and waves
0 to 3 in [LESSONS_FROM_30_LINKS_2026-11-25.md](LESSONS_FROM_30_LINKS_2026-11-25.md), especially
sections 6, 12 and 14). Until then this document exists so the thinking is not lost.

**The question.** What would it take to turn this single-owner tool into a downloadable app with
sign-ups, user privacy and AI insights, for other people's Garmin accounts?

**Evidence labels.** *Verified* = read in a source this session. *Not verified* = my recollection or
an assumption; **prices, limits, legal points and vendor features below are not verified and must be
re-checked before any decision.** This is not legal advice.

## 1. The gate: how to get other people's Garmin data

| Route | Fits a public app? | Notes |
|---|---|---|
| **Garmin's official Connect Developer Program** (Health and Activity APIs, user OAuth, push delivery) | **Yes. The only clean route.** | Requires approval as a business. One commercial connector says it uses the official Health API with OAuth 2.0 and PKCE ([fitness-ai-connector README](https://github.com/fmp-projects/fitness-ai-connector), *verified*). Another project claims individuals are refused ([garmin-givemydata README](https://github.com/nrvim/garmin-givemydata), *not verified*). Our own `sources/personal_api.py` notes the Training API is business-only. A connector's instructions show a mandatory attribution line ("Insights derived in part from Garmin device-sourced data"), suggesting partner rules on branding and probably retention and deletion (*not verified*). |
| **Each user's own Personal API key** | **Doubtful** | Designed for one person's own data and pull-only ([athletedata guide](https://www.athletedata.health/guides/garmin-personal-api-claude-chatgpt), a commercial vendor, plus `sources/personal_api.py`). Whether a service may hold many users' keys is **not verified**; check Garmin's terms. |
| **Users' Garmin email and password (unofficial login)** | **No** | What the Mac setup uses for one person. For a business: terms-of-service and liability risk, bot detection ([project 11](https://github.com/nrvim/garmin-givemydata)), and holding credentials. One hosted service asks for passwords; avoid that model. |

**Consequence.** Apply to the official program **early and in parallel**; its terms are an unknown
that can force design changes. The application itself is cheap and does not commit the owner to build.

## 2. Who holds the data (the central design decision)

| Model | Meaning | Fits Garmin access? | Privacy story | Effort |
|---|---|---|---|---|
| **A. Self-host per user** | Each user deploys their own copy (the one-click model of [Threshold](https://github.com/KareemmSayed/Threshold)) | Yes: own key, personal use | Strongest; the operator holds nothing | Low for the operator, hard for non-technical users |
| **B. Multi-tenant cloud** | A normal sign-up app; the operator holds the data | Needs the official partnership | Standard "trust us, backed by controls" | High |
| **C. Local-first device app** | Analytics and AI on the phone; server only forwards | Partnership still needed (Garmin pushes to servers) | Excellent | Highest; on-device small models on typical phones are unproven |

**View.** B is the only mass-market path. Today's "your data never leaves your Mac" claim does **not**
survive it, so the brand must be chosen consciously (for example "a private cloud with strict controls
and a visible audit trail"). A is a cheap way to test demand with a few technical users, with no data
liability.

## 3. Angles considered
Data-access legality; privacy and security; cost at 10, 1,000 and 100,000 users; speed to build as a
solo developer with AI help; reuse of the existing 17.5k lines of Python; vendor lock-in; AI quality
versus privacy; mobile distribution; operations burden; and whether a business exists at all.

## 4. Architectures compared

| | **1. Python modular monolith + Supabase + Cloudflare** | 2. All-TypeScript on Cloudflare Workers and D1 | 3. Next.js on Vercel + Supabase + serverless | 4. AWS or GCP full stack | 5. Self-host template |
|---|---|---|---|---|---|
| Reuses our Python | **Yes, directly** | No (full port) | Mostly no | Yes | Yes |
| Speed to MVP | Fast | Slow (rewrite) | Fast | Slow | Fastest |
| Cost at start | Low | Lowest | Low | Higher | About zero |
| Tenant isolation | Strong (row-level security) | Per-user tables, more manual | Strong (row-level security) | Strong, most work | Not needed |
| Operations burden | Low to medium | Low | Low | High | Pushed to users |
| Lock-in | Low (standard Postgres) | High | Medium | High | None |
| Main risk | Two moving parts (web and Python) | Rewrite risk | Python analytics awkward on serverless | Over-engineered at the start | Tiny audience |

Option 4 is better kept for a compliance-heavy later phase. Option 2 discards the main asset (the
analytics and validation). Cloudflare Python Workers support and D1 size limits are *not verified*.

## 5. Recommended shape (if pursued)

```
 Phone / browser (installable web app, PWA)
        |  HTTPS
 +------v----------------------------------+
 | Cloudflare: DNS, CDN, WAF, rate limiting |  (also hosts the frontend)
 +------+----------------------------------+
        |
   +----v--------+        +-----------------------------+
   | Frontend    |------->| Supabase Auth (passkeys or  |
   | (Next.js)   |        | email, MFA) issues sessions |
   +----+--------+        +-----------------------------+
        | API (user JWT)
   +----v-----------------------------------------------+
   | Python service (FastAPI), one container, two roles: |
   |  - API: dashboard data, insights, check-ins         |
   |  - Worker: sync jobs, analytics, AI narration       |
   +---+--------------+-------------------+-------------+
       |              |                   |
 +-----v------+ +-----v----------+ +------v------------------+
 | Postgres   | | Object storage | | AI provider              |
 | (Supabase, | | (R2/Supabase)  | | (small model, zero-      |
 | row-level  | | FIT + raw,     | | retention terms) plus    |
 | security,  | | encrypted      | | rule-based fallback      |
 | job queue) | +----------------+ +-------------------------+
 +-----^------+
       | webhooks (Garmin pushes) -> verify -> queue
   Garmin official API (OAuth per user)
```

| Function | Pick | Alternatives considered | Reason |
|---|---|---|---|
| Auth | Supabase Auth | Clerk, WorkOS, Auth0 | Same vendor as the database, so row-level security keys off the signed-in user. Passkey support in Supabase is *not verified*; Clerk or Auth0 are the fallback. |
| Database | Postgres (Supabase) | Neon, Cloud SQL | Plain Postgres, low lock-in; our data is daily rows plus JSON, so no time-series database is needed. |
| Host | Cloudflare for frontend, CDN and security | Vercel, Netlify | **Use one.** Cloudflare already supplies the WAF, bot checks and rate limits. Vercel is smoother only if Next.js-specific features are needed. Netlify is redundant. |
| Python service | Fly.io, Cloud Run or Railway | AWS ECS | One container running unchanged logic; serverless suits Python analytics poorly. |
| Queue | Postgres-based queue | Inngest, Cloudflare Queues | One fewer system at the start. |
| Files | Cloudflare R2 or Supabase Storage | S3 | R2's storage and egress pricing is an assumption to check. |
| AI | Provider abstraction; start with a small hosted open model | Anthropic or OpenAI API, on-device | See section 7. |
| Product analytics | PostHog (EU) or Plausible, **events only, no health values** | | |
| Errors and logs | Sentry with scrubbing; Better Stack or Grafana | | |
| Billing | Stripe or a merchant of record such as Paddle | Razorpay for India | App-store in-app purchase rules and fees apply if shipped to stores (*not verified*). |
| Mobile | PWA first, then wrap with Capacitor | Native | Cheapest route to the stores. |

**Do the functions need those brands?** No. Supabase (login, database, storage), Cloudflare
(hosting and security), one container host and an AI provider cover everything. Vercel plus Netlify
plus Cloudflare is redundant.

## 6. Security and privacy
- **Isolation:** row-level security so one user's query cannot read another's; per-user data keys
  (envelope encryption, a master key in a key service) for raw payloads and Garmin tokens.
- **Tokens:** Garmin OAuth tokens encrypted, never logged, revoked on deletion.
- **Sign-in:** passkeys or email codes plus multi-factor; no passwords of our own.
- **Prompt injection:** activity names and notes are untrusted input. The existing design (Python
  decides; the model only words checked facts; output validated) is an unusual strength here.
- **Logging:** no health values in logs; a separate access audit trail; short retention.
- **Perimeter and process:** WAF, rate limits, bot checks, dependency and secret scanning, code
  scanning, encrypted and restore-tested backups, a penetration test before launch, an incident and
  breach-notification plan.
- **Rights and law (take professional advice):** explicit consent for health data (GDPR treats it as
  a special category; India's DPDP Act applies to the owner), one-click export and full deletion,
  regional hosting choice, privacy policy and terms, no diagnostic claims (wellness framing), age
  limits. US rules for non-HIPAA health apps and app-store health-data policies also apply. **All of
  this is *not verified* here.**

## 7. AI engine
Keep the principle: **Python computes and decides; the model only words checked facts.** That makes a
small, cheap model viable and prompt injection manageable.
- **Start:** a small hosted open model under zero-retention terms, with the rule-based text as
  fallback. Choose the model with the evaluation harness (backlog item A8), not by preference.
- **Premium option:** a frontier model only for the weekly story.
- **Later, optional:** on-device narration for users who want nothing to leave the phone.

## 8. Rough economics (assumptions; verify current prices)
- **Storage:** the single-user copy measured about 55 MB for 18 months (45 MB database plus 11 MB
  FIT files, 23 Nov copy). At 1,000 users that is about 55 GB: a few dollars a month.
- **Compute:** small; a few seconds of work per user per day.
- **AI:** about 5 insights a day at roughly 1,700 tokens each is about 250,000 tokens per user per
  month. A small model at about $0.1 to $0.6 per million tokens costs about $0.03 to $0.15 per user
  per month; a frontier model at about $3 to $15 per million costs about $0.8 to $4. **Model choice
  dominates variable cost.**
- **Fixed:** likely tens to low hundreds of dollars a month at launch.
- **Dominant costs:** legal, security review, support and the owner's time, not servers.

## 9. What carries over from this repository
- **Keeps:** analytics, insight engine, evidence rules, validation design, evaluation scenarios.
- **Must change:** single-user SQLite to tenant-aware Postgres; the unofficial login to official
  OAuth and webhooks; launchd to a queue; static HTML to a per-user app; local Ollama to a hosted or
  on-device model; the "your data stays on your Mac" claim.
- **Already in the backlog and prerequisite:** pure analytics functions (M4), the facts registry
  (K1), the dashboard split (M3), the official-key-only capability test (M1) and the hosted-runner
  item (J1), all in [LESSONS_FROM_30_LINKS_2026-11-25.md](LESSONS_FROM_30_LINKS_2026-11-25.md).

## 10. Staged plan (when the owner chooses to pursue it)
1. **Preconditions:** the quick fixes and waves 0 to 3 are done; M1 has shown what the product looks
   like on official-API data alone.
2. **Cheap early steps (no commitment):** apply to Garmin's developer program; take legal advice on
   health data and the Personal API terms.
3. **Optional validation:** a self-host template for 10 to 20 technical friends, with no data liability.
4. **MVP after approval:** Supabase plus Cloudflare plus one Python container, a closed beta of a few
   dozen users, a penetration test.
5. **Then:** billing, mobile wrapper, scale.

**Not recommended:** storing anyone's Garmin password; a fleet of local-model servers; Kubernetes,
microservices or custom authentication; going native-app first; chasing SOC 2 early.

## 11. Reality check
- **Crowded market.** Hosted connectors already exist; one page claims about 9,000 users in 30 days
  ([missingmcp.com](https://missingmcp.com/garmin), its own claim, *not verified*), and a free
  open-source competitor exists (Threshold). A paid product needs a clear edge; "shows its working,
  checked AI, privacy" is real but not a moat.
- **Platform risk.** Garmin controls access and could bundle similar features.
- **Brand trade-off.** Moving from local-first to cloud changes the privacy promise.

## 12. Decisions needed from the owner (when this is picked up)
1. Is there appetite for a business (support, legal, security obligations), or is a self-host template
   enough?
2. Is a cloud privacy promise acceptable, or must the product stay local-first?
3. Apply to Garmin's developer program now, or only after the nearer-term fixes?
4. Budget for legal advice and a penetration test.

## 13. Open questions and unverified items
Garmin program approval criteria and timeline; whether the Personal API may be used for many users;
all prices and free-tier limits (Supabase, Cloudflare, Vercel, AI providers); Supabase passkey
support; Cloudflare Python Workers and D1 limits; app-store fee rules; all legal and compliance points.
