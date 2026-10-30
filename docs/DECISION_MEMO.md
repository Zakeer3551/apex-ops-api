# Decision memo: Apex Operations API

**Summary:** a deliberately small FastAPI + Postgres service, with effort put into the delivery path instead: tested, scanned, versioned images; a deploy that verifies itself; a rollback that uses the same tested path. Everything runs locally on free tooling (Docker, GitHub Actions, GHCR).

## Assumptions

- "Minimal API" means a few real endpoints with DB persistence, not business features.
- Local Docker Compose stands in for production; no cloud resources are used (the brief forbids paid resources).
- A single host and single API instance are acceptable; high availability is out of scope.
- Reviewers will run on Docker Desktop (macOS/Linux) with internet access to pull from GHCR.
- Synthetic data only.

## Key decisions

| Decision | Why | Alternative considered |
| --- | --- | --- |
| FastAPI + uvicorn | Small and readable; validation and `/docs` built in | Flask (more manual validation) |
| PostgreSQL 16 in Compose, named volume | Real DB and real persistence, not a mock | SQLite (no separate service, less realistic) |
| `python:3.12-slim`, deps installed before code | Smaller attack surface; layer cache makes rebuilds fast | Alpine (wheel/build issues for psycopg) |
| Non-root `appuser` | Limits damage if the app is compromised | Root default |
| Separate `/health` (liveness) and `/ready` (readiness) | A DB blip should hold traffic, not restart a healthy process | One combined check (causes restart loops) |
| Compose runs the **published** image by `API_IMAGE_TAG` | Deploy exactly what CI tested and scanned | Build locally on deploy (untested artifact) |
| Tags `sha-<commit>` + semver, no `latest` | Always know what runs; fixed rollback targets | `latest` (moves; unsafe rollback) |
| Version baked into the image (`ARG` to `ENV`), shown at `/version` | Proof of what actually runs, not what config claims | Version from `.env` (could lie) |
| Rollback = redeploy previous version via `deploy.sh` | One path, tested every deploy | Separate emergency procedure |
| CI: `build-and-push` needs lint, tests and secret scan | Any failure means nothing is published | Publishing then testing |
| Unit tests without DB; integration tests with a real Postgres service in CI | Fast local feedback, real round-trip proof in CI | Mocks only (less confidence) |
| JSON logs to stdout + request IDs | Searchable by field; container-native | Plain text logs |
| Multi-arch image (amd64 + arm64) | Native on cloud servers and on the Apple-silicon dev laptop | amd64 only (emulated locally) |

## Trade-offs I accepted

| Choice | Cost | What I'd do in production |
| --- | --- | --- |
| Secrets as environment variables | Readable via `docker inspect` on the host | File-mounted secrets or a secret store with managed identity |
| Throwaway CI DB password in `ci.yml` | Visible in the repo | Fine for a 1-minute, unreachable test DB; real secrets go in GitHub Secrets / OIDC |
| Lint/tests locally on macOS Python 3.9 | Not the same version as the container (3.12) | CI on 3.12 is the source of truth; could run tests inside a container |
| Table created at app startup | No migration history; app can't start if the DB is unreachable | Alembic migrations as a separate deploy step |
| Manual rollback, not automatic | Needs a human after a FAILED deploy | Auto-rollback on failed readiness, or blue/green |
| Trivy blocks only CRITICAL, reports HIGH | Some HIGH issues can ship | Triage HIGH within an agreed window; `.trivyignore` with reasons |
| Actions pinned to version tags | Tags can be moved or deleted (supply-chain risk) | Pin to full commit SHA, with Dependabot to update |
| `ubuntu-latest` runners | Runner OS changes underneath us (moving to Ubuntu 26) | Pin `ubuntu-24.04`, upgrade deliberately |
| Multi-arch build | CI takes a few minutes longer (QEMU emulation) | Native arm64 runners, or build only the deployed platform |
| Single API container, no restart policy | No HA; manual recovery | 2+ replicas behind a load balancer, platform health probes |

## Security

**Secrets handling**

| Where | How |
| --- | --- |
| Laptop | Secrets only in `.env` (gitignored). `.env.example` has placeholders |
| Code | `DATABASE_URL` read from the environment at runtime; nothing hard-coded |
| Image | `.dockerignore` excludes `.env`; the image is public and contains no secrets |
| Errors/logs | `/ready` says "database unreachable" only; logs record the error *type* only. A unit test asserts the password never appears in the response |
| CI | Image push uses the per-run `GITHUB_TOKEN` (expires after the run). No stored credentials |
| Enforcement | gitleaks scans the full git history on every push and PR |

**In production, passwords would come from** a secret store (Azure Key Vault / AWS Secrets Manager). The app gets its own identity (managed identity / IAM role) that may read only its own secrets, and fetches them at startup. Every read is audited. Rotation means updating the secret and restarting the app, with no code change. Better still for Azure Postgres: passwordless Entra ID authentication. CI would log in to the cloud with OIDC (short-lived, no stored password).

**Least privilege**
- The container runs as non-root.
- The DB port is not published; it's reachable only on the Compose network.
- CI job permissions are limited to `contents: read`, `packages: write`.
- PRs can't publish images.
- Production addition: a dedicated DB user with only the needed table permissions (not the owner/superuser).

**Dependency and image scanning**
- All Python dependencies are pinned. Changes show in review; builds are reproducible. Pinning caught a real problem: `psycopg-binary 3.2.3` had no wheel for macOS/Python 3.9, so it was bumped to 3.2.13 deliberately.
- Trivy scans the built image (OS and Python packages) **before** it is pushed. Policy: report HIGH and CRITICAL, block on CRITICAL, ignore issues with no available fix.
- Next step: Dependabot for `requirements.txt`, the base image and GitHub Actions.

## Metrics and alert proposal

The JSON request logs already contain what's needed; in production I'd also expose a Prometheus `/metrics` endpoint (`prometheus-client`).

| Signal | Metric | Alert | Severity |
| --- | --- | --- | --- |
| Errors | 5xx responses / all responses | > 5% for 5 min | Page |
| Latency | p95 of `duration_ms` | > 500 ms for 10 min | Warn |
| Availability | `/ready` success | failing > 2 min | Page |
| Traffic | requests per minute | drops to 0 during business hours | Warn |
| Saturation | container CPU / memory; DB connections | > 80% for 10 min | Warn |
| Container health | unhealthy status / restarts | any restart loop | Warn |
| DB storage | volume / disk used | > 80% | Warn |

Tooling: Prometheus + Grafana (+ Loki for logs) locally; Azure Monitor + Log Analytics, or CloudWatch, in the cloud. Every alert links to the matching runbook section.

## Cost-aware path to cloud hosting

Goal: a near-zero idle cost at this scale, using managed services so there are no servers to patch. Prices are approximate list prices; check before committing.

| Need | Azure (preferred) | Why cheap | Rough monthly cost |
| --- | --- | --- | --- |
| Run the API | Azure Container Apps, consumption plan | Scales to zero; monthly free grant of compute | ~$0–10 at low traffic |
| Database | Azure Database for PostgreSQL Flexible Server, Burstable B1ms | Smallest managed tier; stop when idle in dev | ~$15–25 |
| Secrets | Key Vault + managed identity | Charged per operation | < $1 |
| Images | GHCR (already used) | Free for public images | $0 |
| Logs/metrics | Log Analytics with a daily cap, short retention | Pay per GB ingested | ~$0–5 |

**Cost guardrails:** a budget alert at a fixed monthly amount; scale-to-zero for non-prod; one region; log retention of 30 days; stop the non-prod DB out of hours; tag every resource for cost tracking. Infrastructure as code (Terraform) so environments can be created and destroyed on demand.

AWS equivalent: App Runner or ECS Fargate, RDS for PostgreSQL `db.t4g.micro`, Secrets Manager, CloudWatch.

## What I'd improve with more time

1. Pre-flight DB check in `deploy.sh`; automatic rollback when readiness fails.
2. Alembic migrations as an explicit deploy step.
3. `/metrics` endpoint + Prometheus/Grafana in Compose.
4. JSON logging for startup errors too.
5. Pin actions to commit SHAs, add Dependabot, enable branch protection requiring CI.
6. Sign images (cosign) and generate an SBOM.
7. Terraform for the Azure path above.
