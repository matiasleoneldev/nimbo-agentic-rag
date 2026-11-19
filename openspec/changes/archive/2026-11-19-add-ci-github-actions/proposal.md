# Proposal

## Why

Lint, type checking, the pytest integration suite and the Playwright E2E suite only run when the author remembers to run them locally on Windows. Nothing proves the project works on a clean machine, and dependency bumps or pull requests merge without any automatic check. A CI pipeline on GitHub Actions closes that gap and gives public visitors of this portfolio a visible pass/fail signal on every commit.

## What Changes

- Add a GitHub Actions workflow, `.github/workflows/ci.yml`, triggered on pushes to `main` and on every pull request. It runs two independent jobs on a GitHub-hosted Ubuntu runner:
  - **backend**: Python 3.14 and Poetry 2, a `pgvector/pgvector:pg17` service container, then `ruff format --check`, `ruff check`, `mypy` and `pytest` against the real database.
  - **frontend**: Node 22, `npm ci`, `npm run lint`, `npm run typecheck`, then the Playwright E2E suite on Chromium.
- The workflow needs no repository secrets. Tests already use a fake LLM and fake embeddings, LangSmith tracing is off in tests, fixture PDFs are generated, and the E2E suite intercepts the chat API.
- LangSmith evals stay out of CI: they call the real OpenAI API and cost credits. They remain a manual step.
- Playwright keeps the Chromium sandbox on locally and turns it off when the `CI` environment variable is set.
- Add a CI status badge to `README.md`.

Business decisions:

- 2026-11-19: CI runs on GitHub Actions and stays provider-agnostic for hosting. Continuous deployment is out of scope until a hosting provider is chosen in its own change.
- 2026-11-19: The Chromium sandbox is disabled in CI only. E2E tests load only this project's own app, and the runner is ephemeral and holds no secrets, so the sandbox protects nothing there. Ubuntu's AppArmor policy can also block it.
- 2026-11-19: CI runs on pushes to `main` and on pull requests, not on pushes to other branches, so a branch with an open pull request is checked once per push instead of twice.
- 2026-11-19: LangSmith evals are excluded from CI to avoid OpenAI costs on every push.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a tooling-only change with no observable behavior change (API contracts, UI, answers), so the change sets `skip_specs: true`.

## Impact

- New file: `.github/workflows/ci.yml`.
- `frontend/playwright.config.ts`: the `chromiumSandbox` launch option depends on the `CI` environment variable.
- `README.md`: CI badge and a short note on what CI runs.
- New external dependencies are GitHub Actions only (checkout, Python/Node setup, Poetry install). The design justifies each one. No runtime or package dependency changes.
- The deployment target stays undecided and nothing couples the code to a provider.
