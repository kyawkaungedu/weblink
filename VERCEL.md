# Vercel-only migration

## Status

Prepared source, not yet runtime-tested or deployed. The execution sandbox was
unavailable during preparation. Do not describe this migration as working/live
until deployment and browser extraction checks succeed.

## Architecture

- `app.py` exports a Flask application; `pyproject.toml` selects it explicitly.
- Static artwork/styles/themes stay in `public/`.
- `/api/collect` gathers the supported post's download rows in one invocation.
- `/api/resolve` resolves at most four rows concurrently, completely inside one
  invocation. No background threads survive the response; no external service,
  database, SnapDeploy account, or persistent job files are needed.
- `vercel-bridge.js` replaces the original browser command transport while
  retaining existing rendering, filters, copy/export, themes and animations.
- State exists only in the current browser tab. Keep the tab open until finished;
  refresh does not resume a job. Cancel/Clear stops future batches and aborts the
  browser request; an already-started server request may finish and consume usage.
- Single rows are not automatically retried in Vercel to keep invocation time
  down. Failed batches retain other results and show per-row failures.
- `server.py` and `Dockerfile` remain unchanged for rollback. No SnapDeploy
  container has been stopped or deleted as part of this migration.

## Deploy

Import `kyawkaungedu/weblink` on Vercel. Use the repo root, Flask framework,
Python 3.12, and the included entrypoint/configuration. No secret environment
variables or paid storage are required. The runtime must support a 60-second
function duration. Applicable Hobby eligibility, quotas and account verification
are subject to Vercel policies; card-free access is not guaranteed for all accounts.

## Required verification

1. Deploy preview and check `/health` reports `vercel-stateless`.
2. Confirm `/` and `/index.html` use `/client.js`; no `/api/start` or `/api/jobs`
   requests should be made by the Vercel client.
3. Exercise movie and multi-season series inputs for HomieTV, YSFlix, RMCMM,
   plus an AdsFly input. Check direct-link rows and resolved rows.
4. Test cancel during collection, cancel during a batch, Clear All during either
   phase, then immediately start a new extraction. Old responses must not repaint.
5. Verify 720p/1080p and server filters, Copy All, row copy, open, TXT download,
   empty startup, desktop/mobile layout, all themes and button animations.
6. Simulate request failures and timeouts; completed results must remain visible.

## Limits and security

No persistent jobs and no shared rate-limit database. Public deployment is still
subject to abuse/usage charges; configure available Vercel usage protections.
Inputs and redirects retain the extractor's site allowlist. Direct destination
URLs are listed, not fetched. Upstream anti-bot policy or access restrictions can
still cause failures on a different hosting network. The 60-second setting is not
a guarantee every upstream request completes in time. Do not log submitted URL
tokens or add API credentials to frontend code.

Official references:
- https://vercel.com/docs/frameworks/backend/flask
- https://vercel.com/docs/functions/runtimes/python
