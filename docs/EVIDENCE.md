# Evidence of execution

Everything below comes from my own runs on a MacBook Air (Apple silicon) and from this repo's GitHub Actions runs, 28–30 Oct 2026. Screenshots are in [`evidence/`](evidence/); full terminal outputs are in [`evidence/logs/`](evidence/logs/). Errors I hit along the way are included, each with its cause and fix.

## Summary

| Brief requirement | Evidence |
| --- | --- |
| 1. API in Docker, health/readiness, non-root | E03, E04, E05, E06 |
| 2. CI: deps, lint/tests, build, blocks on failure | E08, E10, E11, E13, E14, E15, L05 |
| 3. Compose: app + DB, env config, persistence | E05, E06, E07, L01, L02 |
| 4. Versioned release and rollback | E16, E17, E18, L06, L07 |
| 5. Logs, health checks, failure investigation | E19, E20, E21, L09 |
| 6. Security scanning | E22, L08 |
| Problems hit and fixed | E01, E02, L03, L05, E22, L08 |

---

## Setup

**E01: `docker: command not found`** ([e01](evidence/e01-setup-docker-command-not-found.jpg))
- **Problem:** Docker Desktop was installed and showed "running", but the terminal couldn't find the `docker` command.
- **Cause:** the terminal window had been opened before Docker was installed, so it didn't know the new command location (PATH).
- **Fix:** opened a new terminal window.

**E02: Docker working** ([e02](evidence/e02-setup-docker-fixed.jpg))
- `docker --version` reports 29.9.2; `docker compose version` reports v5.6.1.

**L03: pinned package not available** ([log](evidence/logs/L03-pip-psycopg-not-available.txt))
- **Problem:** `pip install` failed: `psycopg-binary==3.2.3` has no package for macOS + Python 3.9.
- **Cause:** that exact pinned version wasn't published for my platform; pip listed the versions that were.
- **Fix:** changed the pin to `3.2.13`, upgraded pip, rebuilt the image. Lint passed afterwards.
- **Why it matters:** pinning made the failure explicit and the fix a deliberate, reviewable change.

## 1. Container, health and readiness

**E03: image build** ([e03](evidence/e03-docker-build.jpg))
- `docker build` of `python:3.12-slim` in 6 steps. Step 6 is `RUN useradd --create-home appuser`, the non-root user. `.dockerignore` is loaded, so `.env` is excluded.

**E04: container serving requests** ([e04](evidence/e04-docker-run-health-docs.jpg))
- `docker run -p 8000:8000`: startup completes, and `GET /health`, `/docs` and `/openapi.json` all return 200.

## 3. Compose with database and persistence

**E05: `docker compose up --build`** ([e05](evidence/e05-compose-up-build.jpg))
- Pulls `postgres:16-alpine`, then creates the `db-data` volume, the network and both containers. Build steps show `CACHED`: the dependency layer was reused because only code changed.

**E06: DB initialises, API waits for it** ([e06](evidence/e06-compose-db-init-api-start.jpg))
- Postgres creates the database ("PostgreSQL init process complete; ready for start up"). Only once the `db` container shows **Healthy** does the API start, which is the `depends_on: service_healthy` setting at work.
- The `initdb: warning: enabling "trust" authentication for local connections` line applies to socket connections *inside* the DB container only. The API connects over the network with a password; the incident drill (E20) shows a wrong password being rejected.

**L01: both containers running** ([log](evidence/logs/L01-compose-containers-day1.txt))
- `db` is `(healthy)` and its port `5432/tcp` is **not** published to the host; only the API's 8000 is.

**L02: validation and persistence** ([log](evidence/logs/L02-items-validation-and-persistence.txt))
- `POST /items` returns 201; an empty name returns 422 with a clear message. After `docker compose down` and `up -d`, all 8 items are still there.

**E07: data after restart** ([e07](evidence/e07-items-persist-after-restart.jpg))
- `GET /items` in the browser after the restart: items 1–8 are present, so the named volume works.

## 2. Lint, tests and CI

**E08: local lint and tests** ([e08](evidence/e08-local-lint-and-tests-pass.jpg))
- `ruff check`: all checks passed. `ruff format --check`: formatted. `pytest -v`: 6 passed.

**E09: intentional failure, locally** ([e09](evidence/e09-local-intentional-failure.jpg)) and [L04](evidence/logs/L04-local-tests-pass-then-fail.txt)
- `/health` deliberately changed to return `"okay"`. `test_health_returns_ok` fails and shows the exact difference (`'okay'` vs `'ok'`). Reverted afterwards.

**E10, E11: first CI run** ([e10](evidence/e10-ci-first-run-lint-and-test.jpg), [e11](evidence/e11-ci-first-run-build.jpg))
- GitHub Actions run #1: `lint-and-test` (install, lint, format check, tests) green, then `build` (Docker image) green.

**E12: integration tests skip locally** ([e12](evidence/e12-local-tests-integration-skipped.jpg))
- Locally: 6 passed, 2 skipped. The skip reason, "needs a real database (set DATABASE_URL)", is intended.

**E13: CI runs integration tests against real Postgres** ([e13](evidence/e13-ci-8-tests-with-real-postgres.jpg))
- In CI on Python 3.12.15, all 8 tests pass, including both integration tests against the Postgres service container. (Later runs have 12 tests.)
- The `anyio ... BlockingPortal` deprecation warning comes from a library (Starlette's test client), not our code. Noted; no action needed.

**E14: failing test blocks release** ([e14](evidence/e14-pr-intentional-failure-blocked.jpg))
- PR #1 "Demo: intentionally break /health to prove CI blocks release": `CI / lint-and-test` **failing**, `CI / build-and-push` **skipped**. No image was built or published. The PR is left open and unmerged as evidence.

**E15: the failing test in CI** ([e15](evidence/e15-ci-intentional-failure-log.jpg))
- CI log: `FAILED tests/test_api.py::test_health_returns_ok`, `1 failed, 7 passed`, `Process completed with exit code 1`. In the left panel, `build-and-push` shows as skipped.

**L05: CI caught unformatted code** ([log](evidence/logs/L05-ci-format-check-failure.txt))
- **Problem:** after adding `/version`, CI `lint-and-test` failed (exit code 1).
- **Cause:** `ruff format --check` found 2 files not in the standard format. Tests themselves passed.
- **Fix:** ran `ruff format .` and committed; CI green. Since then I run `ruff format . && ruff check . && pytest` before every push.

## 4. Release and rollback

**L06: first versioned deploy** ([log](evidence/logs/L06-deploy-1.0.0.txt))
- `./scripts/deploy.sh 1.0.0` pulls the CI-published image from GHCR, starts it, waits for `/ready`, and reports `{"version":"1.0.0"}`, read from inside the image.

**L07: deploy 1.1.0, roll back to 1.0.0, twice** ([log](evidence/logs/L07-deploy-and-rollback.txt))
- Each step reports what was running before and what is running now, and each completed in about 6 s.
- Image digests differ (1.0.0 = `d8fe51…`, 1.1.0 = `fa41b2…`). The rollback returns to the exact same image bytes, not a rebuild.

**E16: new feature live on 1.1.0** ([e16](evidence/e16-v1.1.0-get-item-works.jpg))
- `GET /items/1` returns `{"id":1,"name":"string"}`. This endpoint exists only from 1.1.0.

**E17: after rollback, the 1.1.0 feature is gone** ([e17](evidence/e17-rollback-v1.0.0-route-gone.jpg))
- Same URL returns `{"detail":"Not Found"}`, FastAPI's response for a route that doesn't exist. Version 1.0.0 is really running. (A missing *item* on 1.1.0 would say `"item not found"`.)

**E18: data intact after rollback** ([e18](evidence/e18-rollback-data-intact.jpg))
- `GET /items` still returns items 1–8. Rollback replaced only the app container; the database and volume were untouched.

## 5. Logs, health checks and failure investigation

**L09: structured logs, health, incident** ([log](evidence/logs/L09-deploy-1.2.0-logs-and-incident.txt))
- Deploy 1.2.0 succeeds. `docker compose logs api` shows one JSON line per request (`time`, `level`, `event`, `method`, `path`, `status`, `duration_ms`, `request_id`). The `/health` line nobody requested is Docker's own health check.
- `docker compose ps` shows both `api` and `db` as `(healthy)`.
- It then contains the full incident drill below.

**E19: incident detected** ([e19](evidence/e19-incident-deploy-failed.jpg))
- **Drill:** wrong password put into `DATABASE_URL`, then deploy.
- **Result:** `FAILED: 1.2.0 is not ready. Roll back with: ./scripts/rollback.sh`. The readiness gate refused to report success.

**E20: investigation** ([e20](evidence/e20-incident-investigation.jpg))
- `docker compose ps -a` shows `api` **Exited (3)** while `db` is **Up (healthy)**. The database is fine, so the problem is on the app side.
- `docker compose logs api` shows `psycopg.OperationalError: ... FATAL: password authentication failed for user "apex"`, then `Application startup failed. Exiting.`
- **Root cause:** wrong credentials in config. The password value itself does not appear in the logs.

**E21: fixed** ([e21](evidence/e21-incident-fixed.jpg))
- Correct password restored in `.env`, redeployed. `SUCCESS. Running: {"version":"1.2.0"}`. About 2 minutes from detection to fix.
- Lessons (also in the [runbook](RUNBOOK.md#incident-report-wrong-database-password)): image rollback would not have fixed a config fault; startup errors aren't JSON yet; add a pre-flight DB check to `deploy.sh`.

## 6. Security scanning

**E22: scanner step failed to load** ([e22](evidence/e22-ci-trivy-action-not-found.jpg)) and [L08](evidence/logs/L08-ci-trivy-action-not-found.txt)
- **Problem:** after adding Trivy, `build-and-push` failed with `Unable to resolve action aquasecurity/trivy-action@0.28.0`.
- **Cause:** the action's version tags start with `v` (`v0.28.0`). On the first fix attempt only one of the two references was changed, and still without the `v`.
- **Fix:** both references set to `@v0.36.0`; `build-and-push` green.
- **Why it's safe:** the pipeline stopped before running anything, so nothing was published.
- **Lesson:** pin third-party actions exactly, ideally to a commit SHA.
- The same screen shows `secret-scan` (gitleaks) ran and produced its `gitleaks-results.sarif` report. The warnings are GitHub notices about Node.js 20 being deprecated in `checkout@v4`, `setup-python@v5` and `gitleaks-action@v2`, and about `ubuntu-latest` moving to Ubuntu 26. They're harmless now, and listed as follow-ups in the [decision memo](DECISION_MEMO.md#trade-offs-i-accepted).
