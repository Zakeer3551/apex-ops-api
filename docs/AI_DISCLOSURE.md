# AI-use disclosure

I used **Claude (Anthropic)** throughout this assessment as a tutor and pair-programmer, in a chat session. This page lists what it did and what I did, so the work is not presented as entirely independent.

## What Claude did

- **Planning:** broke the brief into steps, mapped each requirement to a deliverable, and proposed the stack (FastAPI, Postgres, pytest, ruff, GitHub Actions, GHCR, gitleaks, Trivy).
- **Explanations:** taught me concepts I had not used hands-on before: APIs and endpoints, liveness vs readiness, linting, unit vs integration tests, CI job dependencies, image tagging, structured logging, secret handling.
- **Code drafts:** wrote the first versions of `app/main.py`, the tests, `Dockerfile`, `compose.yaml`, `.github/workflows/ci.yml`, `scripts/deploy.sh` and `scripts/rollback.sh`, which I typed into the repo, ran and adjusted.
- **Debugging help:** helped interpret errors I hit (below).
- **Documentation drafts:** drafted this README, the runbook, the decision memo and this disclosure from my notes and the actual command outputs. I reviewed and edited them.

## What I did

- Set up the environment (Docker Desktop, GitHub repo, Python venv) and ran every command myself on my own machine.
- Ran every demo and captured all evidence in `docs/evidence/`: deploys, rollbacks, the intentional CI failure PR, the DB-down test, the wrong-password incident drill.
- Hit and fixed real problems during the work:
  - `docker: command not found` after install (fixed with a new terminal session)
  - `psycopg-binary==3.2.3` not available for my Mac/Python (bumped the pin to 3.2.13)
  - CI failing on `ruff format --check` (formatted, and added a pre-push habit)
  - CI failing on a wrong `trivy-action` version reference (fixed to `v0.36.0`)
- Made the final calls on scope and trade-offs, and reviewed each file so I can explain it line by line in the review.

## What was not AI-generated

All execution results, logs and screenshots are from my own runs. No output was written or edited by AI to look like a run happened.
