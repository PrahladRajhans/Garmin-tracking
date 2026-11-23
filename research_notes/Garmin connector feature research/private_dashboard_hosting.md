# Private dashboard hosting review — 23 November 2026

This is source research for ROADMAP item A, not a second plan. No user health data has been
uploaded. The existing local/iCloud build remains the default.

| Option | Updates after sync | Mac must stay on to view | Privacy and current evidence |
|---|---|---|---|
| Cloudflare Pages + Access | Optional Wrangler upload implemented | No; last uploaded snapshot remains available | Preferred candidate. Both production and all preview addresses need Access. Live account setup, owner OTP and phone tests pending |
| Tailscale Serve | Serves the current file | Yes, awake and connected | Candidate if keeping health data off a web host is preferred. Current pricing and Mac/device behavior not verified here; do not use public Funnel |
| iCloud Drive copy | Already in `dashboard.build` when the iCloud directory exists | Needed to build/sync, not necessarily to view an already downloaded file | File copy confirmed in code only. Mac iCloud availability and iPhone Files/Safari links remain unverified |
| Private Claude Artifact | Manual snapshot | No after sharing | Not an automatic sync destination. Host access controls and availability need confirmation |
| Public GitHub Pages / public static URL | Irrelevant | Irrelevant | Excluded by the owner's privacy requirement |

## What the official sources establish

Cloudflare's documentation source was retrieved from its official GitHub repository at
`01690abe7b447f3a09c85af6e06d2e9fbc8f5c8c` (`production`, retrieved 23 November 2026).
The published documentation and pricing sites were blocked by the cloud network policy.

- [Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
  ([source](https://github.com/cloudflare/cloudflare-docs/blob/01690abe7b447f3a09c85af6e06d2e9fbc8f5c8c/src/content/docs/pages/platform/limits.mdx)):
  Free lists **500 builds/month**, one simultaneous build, **20,000 files**, and **25 MiB/file**.
  The helper uploads two files. The 500 figure is labeled builds; this review does not assume
  it establishes a separate Direct Upload deployment quota. Even an upload at each 3-hour run
  is 248 in a 31-day month, before manual builds; the actual gate usually runs fewer syncs.
- [Preview deployments](https://developers.cloudflare.com/pages/configuration/preview-deployments/)
  ([source](https://github.com/cloudflare/cloudflare-docs/blob/01690abe7b447f3a09c85af6e06d2e9fbc8f5c8c/src/content/docs/pages/configuration/preview-deployments.mdx)):
  “By default, these deployment URLs are public.” The built-in Access switch protects previews,
  **not** the production Pages domain or custom domains. Hash URLs and branch aliases persist.
- [Protecting production too](https://developers.cloudflare.com/pages/platform/known-issues/#enable-access-on-your-pagesdev-domain)
  ([source](https://github.com/cloudflare/cloudflare-docs/blob/01690abe7b447f3a09c85af6e06d2e9fbc8f5c8c/src/content/docs/pages/platform/known-issues.mdx)):
  remove the wildcard from the first Access application to protect production, then re-enable
  preview protection. Review that **two** apps exist. Custom domains need separate protection;
  this helper refuses projects with custom domains rather than attempting to manage them.
- [Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/)
  ([source](https://github.com/cloudflare/cloudflare-docs/blob/01690abe7b447f3a09c85af6e06d2e9fbc8f5c8c/src/content/docs/pages/get-started/direct-upload.mdx)):
  supports prebuilt local assets via Wrangler. Running Wrangler inside a directory with
  `functions/` can include those functions. The helper therefore uses a fresh staging directory
  outside the checkout and copies only the HTML and fixed `_headers` file.
- [Cloudflare One overview](https://developers.cloudflare.com/cloudflare-one/)
  ([source](https://github.com/cloudflare/cloudflare-docs/blob/01690abe7b447f3a09c85af6e06d2e9fbc8f5c8c/src/content/docs/cloudflare-one/index.mdx)):
  confirms Free and Paid plans exist, but does **not** state a current Access seat allowance.
  The [pricing page](https://www.cloudflare.com/plans/zero-trust-services/) could not be read.
  **Do not repeat an unverified “50 users” allowance.** Confirm free eligibility and allowances
  in the owner's account before activating hosting. The project promises no paid subscription.

The installed official `cloudflare` Python package **5.10.0** was inspected outside the project
to verify API fields and routes: Pages `subdomain`, `production_branch`, `domains`, `source`;
Access `destinations[].uri`/`overrides`, `domain`, `self_hosted_domains`,
`options_preflight_bypass`; application policy `decision` and exact `email.email` Include rule.
It is **not** a new project dependency. The helper uses Python's standard HTTP library, does
not follow authenticated API redirects, and never includes provider response bodies in errors.
Wrangler **4.166.0** was installed separately; its version and `pages deploy --help` verified
the command and flags. No live deployment was attempted.

## Activation and verification limits

The helper is intentionally narrow: dedicated Direct Upload project, no custom domains, two
whole-host self-hosted Access apps, one exact-email Allow policy each, no overlapping paths,
destination overrides, or bypass rules. It checks all application-list pages, reads the matching
apps/policies, and requires anonymous production and wildcard requests to redirect to Access.
Only then can Wrangler upload. Setup uses a non-health placeholder until these checks succeed.
`python -m garmin_mcp.publish --check` performs those checks without an upload.

The token needs account-scoped Pages Edit plus Access apps/policies Read; the helper does not
create or edit Access applications. Set up One-time PIN in the account UI. A successful
configuration check does not prove the owner's login works: test anonymous denial, a different
email's denial, the owner's OTP login, production and direct deployment links, page/run links,
and a subsequent scheduled update on the actual devices. Account changes after an upload can
affect existing copies; leave their Access protection in place.

See `MAC_SETUP.md` for the minimal owner actions and instructions for the local assistant.

### November follow-up

[Cloudflare One setup](https://developers.cloudflare.com/cloudflare-one/setup/) documents a
Zero Trust Free plan. The fetched [Zero Trust plans page](https://www.cloudflare.com/plans/zero-trust-services/)
does not give a seat allowance in its visible public text. The account UI is the remaining
check. [Tailscale Serve](https://tailscale.com/kb/1312/serve) documents private service access
inside a tailnet. It is the alternative if you prefer serving directly from an awake Mac.
The Pages snapshot serves while the Mac is offline. iCloud is the simplest first device test
for an Apple-only workflow. Cloudflare account configuration and live upload remain pending.
