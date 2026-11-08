# Link Lab

Standard-library Python backend with a static Burmese-language interface.

## Run locally

Use Python 3.12 (the Docker target):

```sh
cd deploy-link-unwrapper
python3 server.py
```

Open `http://localhost:8080`. Set `PORT` to change the listening port. The app needs write access to its `link-jobs/` directory. No Python packages are required.

## Container deployment

From this directory:

```sh
docker build -t link-lab .
docker run --rm -p 8080:8080 link-lab
```

These are deployment instructions, not a claim that a Docker build was tested. Put a public deployment behind HTTPS. Source changes in this release were not deployed to an external service.

## Supported inputs

- HomieTV / YSFlix movie and TV-show post URLs.
- RMCMM movie and TV-show post URLs with supported download tables.
- AdsFly links.
- xxxmmsub item or listing-page URLs. Card discovery uses the submitted HTML; API fallback supports page-only home/items listings and country listings. Unsupported filters fail visibly instead of being replaced by global results.

## Important limits

At most 400 result rows per job and 100 xxxmmsub cards per listing. Failed cards appear as failed result rows; their unavailable download-link count cannot be known. MegaUp is prioritized without removing other servers.

Cancellation cannot interrupt an already-running network request. RMCMM heading/table/link season markers are supported; separate season pages and AJAX-loaded seasons are not automatically traversed.

Job access expires after two hours and is lost on restart. Old job files are removed on a later job start, not by a timed deletion guarantee. Copy or export useful results.

External CDN styles/fonts require network access. Link extraction does not download files or certify their safety. Provider compatibility was checked with offline fixtures, not live-provider requests.

See the accompanying `tests/` folder for regression tests, `validation/` for results and the change diff, and `RELEASE-NOTES.md` for review notes.
