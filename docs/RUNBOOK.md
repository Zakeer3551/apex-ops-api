# Runbook: Apex Operations API

For whoever is operating the service. All commands run from the repo root on the Docker host.

## Quick reference

| Task | Command |
| --- | --- |
| What's running? | `docker compose ps` and `curl -s localhost:8000/version` |
| Is it healthy? | `curl -i localhost:8000/health` and `curl -i localhost:8000/ready` |
| Logs | `docker compose logs api --tail 50` (add `-f` to follow) |
| Errors only | `docker compose logs api \| grep '"level": "error"'` |
| One request | `docker compose logs api \| grep <request-id>` |
| Deploy | `./scripts/deploy.sh <version>` |
| Roll back | `./scripts/rollback.sh` |
| Stop (keep data) | `docker compose down` |

---

## 1. Deploy

**Before:** the version's CI run (tag `v<version>`) is green, and the image exists in GHCR.

```bash
./scripts/deploy.sh 1.2.0
```

What happens:

1. Pulls `ghcr.io/zakeer3551/apex-ops-api:1.2.0`. If the pull fails, nothing is changed.
2. Saves the currently running version to `.previous-version`.
3. Sets `API_IMAGE_TAG=1.2.0` in `.env`.
4. Recreates only the `api` container. The DB and its data are untouched.
5. Polls `/ready` every 2 s for up to 30 s.

**Success:** `==> SUCCESS. Running: {"version":"1.2.0"}`

**Failure:** `==> FAILED: 1.2.0 is not ready.` Go to [Incident response](#3-incident-response). Decide: roll back (if the new image is at fault) or fix config (if config is at fault).

**After:** run `docker compose ps`; both containers should show `(healthy)` within about 20 s.

## 2. Rollback

Use when a newly deployed **image** is broken.

```bash
./scripts/rollback.sh
```

This redeploys the version in `.previous-version` through the same `deploy.sh`, with the same pull and readiness checks. To go to any specific version: `./scripts/deploy.sh 1.0.0`.

**Check:** `curl -s localhost:8000/version` shows the old version and `curl -s localhost:8000/items` still returns the data.

**Limits:**
- Rollback restores the **image only**, not `.env` config. If the fault is config (wrong password, wrong URL), rollback will not fix it; fix the config instead (see the incident report below).
- There are no DB schema migrations yet. If a future version changes the schema, rolling back the app may need a matching DB rollback.

Tested: 1.0.0 → 1.1.0 → rollback → 1.0.0, twice, about 6 s each, data intact ([L07](evidence/logs/L07-deploy-and-rollback.txt), [E16–E18](EVIDENCE.md#4-release-and-rollback)).

## 3. Incident response

1. **Confirm the impact:** `curl -i localhost:8000/health` and `/ready`. Note the time.
   - `/health` fails means the app process is down.
   - `/health` OK but `/ready` 503 means the app is up but can't reach the DB.
2. **Check containers:** `docker compose ps -a` (`-a` shows exited containers). Note the status and exit code.
3. **Read the logs:** `docker compose logs api --tail 50`, then `docker compose logs db --tail 50`. Look for `"level": "error"`, `readiness_failed`, `FATAL`, `Traceback`.
4. **Ask "what changed?"** A recent deploy (`cat .previous-version`, `grep API_IMAGE_TAG .env`) or a config edit.
5. **Mitigate first:**
   - Caused by a new image: `./scripts/rollback.sh`.
   - Caused by config: fix `.env`, then `./scripts/deploy.sh <current version>`.
   - DB down: `docker compose start db`, then wait for healthy.
6. **Verify:** `/ready` is 200, `docker compose ps` is healthy, and logs show 200s.
7. **Write it up** using the format of the incident report below: timeline, cause, fix, prevention.

## 4. Troubleshooting

| Symptom | Likely cause | Check | Fix |
| --- | --- | --- | --- |
| `docker: command not found` | Terminal opened before Docker was installed / PATH | `which docker` | Open a new terminal window; or Docker Desktop, Settings, Advanced, System |
| `Set API_IMAGE_TAG in .env` | `.env` missing or incomplete | `cat .env` | `cp .env.example .env` |
| Deploy: pull fails, `not found` | Version not published, or typo | GHCR package page / Actions run for the tag | Use an existing version; wait for the tag's CI run |
| Deploy FAILED, api `Exited (3)` | App crashed on startup, usually DB auth | `docker compose logs api` | Fix `DATABASE_URL` in `.env`, redeploy |
| `/ready` 503, `/health` 200 | DB stopped or unreachable | `docker compose ps`, `docker compose logs db` | `docker compose start db` |
| `password authentication failed` | `DATABASE_URL` password does not match DB | Compare with `POSTGRES_PASSWORD` | Correct `.env`. Note: changing `POSTGRES_PASSWORD` does not change an existing DB's password; the volume keeps the original |
| Port 8000 already in use | Another process or old container | `lsof -i :8000` | Stop it, or `docker compose down` |
| Data gone after restart | `down -v` was used (deletes the volume) | `docker volume ls` | Use `docker compose down` without `-v` |
| CI: `Unable to resolve action` | Wrong action version reference | Annotation in the Actions run | Use the exact tag, e.g. `@v0.36.0` |
| CI: format check fails | Code not formatted | `ruff format --check .` | `ruff format .`, commit |
| CI: `build-and-push` skipped | A test, lint or secret scan failed (working as intended) | The red job's log | Fix the cause; never bypass |

---

## Incident report: wrong database password

**Date:** 2026-10-30, about 15:55 IST. **Evidence:** [E19–E21](EVIDENCE.md#5-logs-health-checks-and-failure-investigation). **Type:** controlled drill. **Duration:** about 2 minutes to resolve.

**What happened:** `DATABASE_URL` in `.env` was changed to a wrong password, then `./scripts/deploy.sh 1.2.0` was run, simulating a bad config change shipped with a deploy.

**Detection:** the deploy script's readiness gate printed `FAILED: 1.2.0 is not ready` after 30 s. It did not falsely report success.

**Investigation:**
1. `docker compose ps -a` showed `api` `Exited (3)` while `db` was `Up (healthy)`. So the DB was fine and the problem was on the app side.
2. `docker compose logs api --tail 30` showed `psycopg.OperationalError: ... FATAL: password authentication failed for user "apex"`, then `Application startup failed. Exiting.` The app tries the DB at startup to create its table, so bad credentials stop it from starting.

**Root cause:** wrong credentials in `DATABASE_URL` (config drift). Not a code or image defect.

**Fix:** restored the correct password in `.env`, then ran `./scripts/deploy.sh 1.2.0`, which reported SUCCESS. `/ready` returned 200.

**What went well:**
- The readiness gate caught it; no false "success".
- The password value never appeared in logs.
- The logs pointed straight at the cause.

**What we learned:**
- `rollback.sh` would **not** have fixed this: it rolls back the image, but the fault was config.
- Startup errors print as a plain-text traceback, not JSON, so structured logging doesn't cover startup.
- There is no restart policy. That's acceptable here, because restarting can't fix bad credentials.

**Prevention / follow-ups:**
- Add a pre-flight DB connection check to `deploy.sh` *before* swapping the container.
- Keep config and secrets in a versioned secret store, so config changes are reviewed and can be rolled back.
- Make startup errors log as JSON.
- Alert on `/ready` failing for more than 2 minutes.
