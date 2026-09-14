# Updating the activity card

Run this on the Mac where Codex is signed in, using Python 3.9 or later:

```sh
python3 scripts/update_activity.py --expected-profile lilymiao
```

To refresh, commit only the three generated files, and publish to this profile repository:

```sh
python3 scripts/update_activity.py --expected-profile lilymiao --publish
```

Automatic publishing requires a clean `main` branch and an authenticated Git remote. It pulls with `--ff-only`, never force-pushes, and checks that the remote revision matches. A failed push can be retried without generating a duplicate commit. The expected Codex profile check prevents publishing from a different signed-in account.

## Data source and limitations

The installed Codex desktop app on 2026-09-14 obtains profile statistics from `GET https://chatgpt.com/backend-api/wham/profiles/me`. This is a private, undocumented endpoint, not a supported public integration API. It may change or stop working. The script uses the existing local Codex login and does not renew credentials itself. Open Codex and sign in again if authentication expires.

The script publishes a strict allowlist: source statistics date, lifetime tokens, peak daily tokens, current and longest streaks, and daily token totals. It does not publish credentials, account IDs, conversations, task titles, plugin usage, or raw API responses. It does not request or publish billing data.

Dates and streaks are passed through from the source. The source does not specify its bucket timezone; there is no invented timezone conversion. The statistics date is the provider's cutoff label and need not mean the current day is complete. The first export was dated 2026-09-14, with the latest nonempty daily bucket on 2026-09-13.

Daily totals must reconcile exactly with lifetime and peak counts before any output is written. Missing statistics, profile mismatches, or schema changes leave the last successful card in place. SVG content is deterministic, so rerunning against unchanged source statistics creates no changes.

The heatmap shows 52 Sunday-first calendar columns ending in the source statistics week. Future dates are omitted. The four nonzero color levels follow the app's current rule: 0–25%, over 25–50%, over 50–75%, and over 75% of the maximum daily count in the displayed period. Only active days receive color; days absent from the source's sparse history display as zero, matching the app.

Credentials must stay on the local computer. Do not put `auth.json`, access tokens, refresh tokens, or session logs in the repository or GitHub Actions secrets. A hosted GitHub Actions job cannot refresh this local-login data on its own.
