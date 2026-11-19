# Design

## Context

- Locally, the backend suite needs the `db` service from `docker-compose.yml`. Its `docker/init-db.sql` creates the `nimbo_test` database and the `vector` extension. `tests/conftest.py` connects through `TEST_DATABASE_URL` (default `postgresql+asyncpg://nimbo:nimbo@localhost:5432/nimbo_test`) and loads `backend/.env` only if it exists.
- Tests build `Settings` and `PGEngine` themselves and pass them to `create_app`. LLM and embeddings are fakes (`tests/fakes.py`), and LangSmith tracing is forced off. Help-center PDFs are generated per test (`tests/help_center_factory.py`). So the suite needs no OpenAI or LangSmith credentials and no `nimbo-help-center/` corpus.
- `poetry.toml` puts the venv in `backend/.venv`, and the lock file needs Poetry 2.
- The Playwright suite builds the frontend and serves it on `127.0.0.1:3100`. It intercepts the chat API with `page.route`, so it needs no backend. It currently forces `chromiumSandbox: true`.
- The repository is hosted on GitHub (`origin`).

## Goals / Non-Goals

**Goals:**
- One workflow file that runs the same commands the README documents, with no repository secrets.
- Fail fast and independently: a frontend failure does not hide a backend result.

**Non-Goals:**
- Continuous deployment or anything tied to a hosting provider.
- LangSmith evals, the ingestion command, or anything that calls the real OpenAI API.
- A Windows runner. Docker service containers only exist on Linux runners, and the Windows constraint stays covered by local development.
- Branch protection rules. That is a GitHub repository setting the author can enable by hand, not a file in this repo.

## Decisions

### Two parallel jobs in one workflow (`ci.yml`)
Backend and frontend share no state: E2E mocks the API. Separate jobs run in parallel and report separately. Alternative: one job running everything. It is simpler, but slower, and the first failure hides the rest. Alternative: two workflow files. That gives two badges and duplicated triggers for no gain.

### Triggers: `push` to `main` and `pull_request`
`push` is filtered to `branches: [main]`, and `pull_request` is unfiltered. This covers direct pushes to `main` and every pull request, including Dependabot ones, and runs once per event. Alternative: unfiltered `push`. It also checks branches without a pull request, but runs twice for every push to a branch with an open pull request. A `concurrency` group cancels superseded runs on the same ref.

### Postgres as a job service container, extension created by a step
The backend job declares `pgvector/pgvector:pg17` as a service with `POSTGRES_DB: nimbo_test`, the same `nimbo`/`nimbo` dev credentials, port `5432`, and a `pg_isready` health check. Services start before checkout, so `docker/init-db.sql` cannot be mounted. A step runs `CREATE EXTENSION IF NOT EXISTS vector` through `psql`, which is preinstalled on Ubuntu runners. Alternative: `docker compose up -d db` inside the job. It reuses the init script, but duplicates the healthcheck wait by hand and needs both databases for no reason. The dev credentials are not secrets: the container only lives inside the ephemeral runner.

### Poetry installed with `pipx`, not a third-party action
`pipx` is preinstalled on GitHub's Ubuntu runners. `pipx install poetry==2.2.1` pins the same Poetry the README requires, without adding a third-party action. `actions/setup-python` with `cache: poetry` caches dependencies keyed on `poetry.lock`. Poetry must be on `PATH` before that step, so `pipx install` comes first.

### Actions used (new dependencies, justified)
- `actions/checkout`: needed to get the code. GitHub-maintained.
- `actions/setup-python`: installs Python 3.14, the version `pyproject.toml` requires, and provides the Poetry cache. GitHub-maintained.
- `actions/setup-node`: installs Node 22, the README's minimum, and caches npm keyed on `frontend/package-lock.json`. GitHub-maintained.
No third-party actions. Each one is pinned to a major version tag. Commit-SHA pinning is a possible hardening later, but this workflow has no secrets or write permissions to steal, so the gain is small. The workflow sets `permissions: contents: read`.

### Frontend job
`npm ci` (lock-file exact), `npm run lint`, `npm run typecheck`, `npx playwright install --with-deps chromium`, `npm run test:e2e`. Only Chromium, because both Playwright projects use Desktop Chrome. On failure, the Playwright report and `test-results/` are uploaded as an artifact (`actions/upload-artifact`, GitHub-maintained) so failures can be diagnosed without rerunning.

### Chromium sandbox off in CI only
`playwright.config.ts` sets `chromiumSandbox: !process.env.CI`. GitHub sets `CI=true` on every runner. Rationale: see the proposal's business decision of 2026-11-19. Alternative: keep the sandbox and relax the runner's AppArmor user-namespace restriction with `sysctl`. That also weakens a kernel protection, only on a throwaway VM, and it hides the exception outside the config where the original choice lives. Locally (Windows) the sandbox stays on as before.

### README badge
A status badge for `ci.yml` goes under the README title, plus one line in the commands section saying CI runs the same checks.

## Risks / Trade-offs

- [Some test or settings path needs an env var that only exists in the local `backend/.env`] → The first CI run reveals it. Fix it by setting a non-secret placeholder in the workflow's `env`, or by fixing the test. Never by adding a real secret.
- [Python 3.14 or Poetry 2.2.1 behaves differently on Linux than on Windows] → That is exactly what CI is meant to surface. Fix it in code, not by skipping checks.
- [`next build` plus two Playwright projects is slow on a 2-vCPU runner] → `workers: 2` already matches the runner. The npm cache and installing only Chromium keep setup short.
- [Flaky E2E tests turn CI red without a real regression] → Treat the first flaky failure as a test bug. No automatic retries are added up front.
- [The CI badge shows red publicly while `main` is broken] → Accepted: that is the point of the signal.

## Migration Plan

Additive. Push the workflow on a branch, confirm both jobs pass on the pull request, then merge. To roll back, delete `.github/workflows/ci.yml` and the badge line.
