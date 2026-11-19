# Tasks

Scenario traceability: this change has no spec deltas (`skip_specs: true`), so there are no scenarios to trace. The CI run itself verifies the work: every existing pytest and Playwright test must pass on the runner.

## 1. Playwright config

- [x] 1.1 In `frontend/playwright.config.ts`, change `chromiumSandbox: true` to `chromiumSandbox: !process.env.CI`. Rewrite the comment above it so it says the sandbox stays on locally and is off in CI, with the reason in one line (the tests only load this project's own app, and the runner is ephemeral, holds no secrets and may block the sandbox through AppArmor). Verify with `npm run lint ; npm run typecheck ; npm run test:e2e` in `frontend/`: all pass locally with the sandbox still on, since `CI` is unset.

## 2. Workflow

- [x] 2.1 Create `.github/workflows/ci.yml` as design.md describes:
  - Name `CI`; triggers `push` with `branches: [main]` and an unfiltered `pull_request`; a `concurrency` group per ref with `cancel-in-progress`; `permissions: contents: read`.
  - Job `backend` (`ubuntu-latest`, `working-directory: backend`):
    - Service `pgvector/pgvector:pg17` with `POSTGRES_USER`/`POSTGRES_PASSWORD` `nimbo`, `POSTGRES_DB: nimbo_test`, port 5432 and a `pg_isready` health check.
    - Steps in order: `pipx install poetry==2.2.1`, `actions/setup-python` (3.14, `cache: poetry`), a `psql` step that runs `CREATE EXTENSION IF NOT EXISTS vector` on `nimbo_test`, `poetry install`, `poetry run ruff format --check .`, `poetry run ruff check .`, `poetry run mypy .`, `poetry run pytest`.
    - `TEST_DATABASE_URL=postgresql+asyncpg://nimbo:nimbo@localhost:5432/nimbo_test` set in the job env.
  - Job `frontend` (`ubuntu-latest`, `working-directory: frontend`): `actions/setup-node` (22, npm cache on `frontend/package-lock.json`), then `npm ci`, `npm run lint`, `npm run typecheck`, `npx playwright install --with-deps chromium`, `npm run test:e2e`. On failure, upload `playwright-report/` and `test-results/` with `actions/upload-artifact`.
  - Verify: the YAML parses, for example with `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`, and every command in it matches one in README.md.
- [x] 2.2 Push the branch, open a pull request and confirm both jobs pass on GitHub. In the frontend job log, confirm Playwright ran both projects (`phone`, `desktop`). If a job fails because something only exists in the local `backend/.env`, add a non-secret placeholder to the workflow `env`, or fix the test, per the design's risks. Never add a real secret. Verify: green checks on the pull request.

## 3. Documentation

- [x] 3.1 Add the CI status badge for `ci.yml` under the README title, linking to the workflow's Actions page. Add one line to the README commands section saying CI runs the same backend and frontend checks on pushes to `main` and on pull requests, and that LangSmith evals stay manual. Verify: the badge renders on the pull request's README preview and points to the passing run.
