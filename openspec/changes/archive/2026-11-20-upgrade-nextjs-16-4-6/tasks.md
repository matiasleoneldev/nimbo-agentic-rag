# Tasks

Scenario traceability: this change has no spec deltas (`skip_specs: true`), so there are no scenarios to trace. The existing lint, typecheck and Playwright suites verify the work, locally and in CI.

## 1. Dependency bump

- [x] 1.1 In `frontend/`, run `npm install --save-exact next@16.4.6 eslint-config-next@16.4.6`. Verify: `package.json` shows `"next": "16.4.6"` and `"eslint-config-next": "16.4.6"`, both without `^`, and `npm ls next eslint-config-next @next/eslint-plugin-next` reports 16.4.6 for all three.
- [x] 1.2 Run `npm audit fix` without `--force`, then read the `package-lock.json` diff. Verify: `package.json` ranges did not change; the lock-file changes are limited to `next`, `@next/*`, `eslint-config-next` and the lint tooling (`typescript-eslint`, `@typescript-eslint/*`, `minimatch`); `npm audit` lists no `next` entry. If unrelated runtime packages moved, follow the design's fallback (revert the lock file, then `npm update typescript-eslint`). Other remaining advisories are acceptable when they come from dev-only transitive packages with no fix inside the declared ranges: list them in the pull request description instead of forcing a fix.

## 2. Local verification

- [x] 2.1 In `frontend/`, run `npm run lint ; npm run typecheck ; npm run test:e2e`. Verify: all three pass. The E2E run builds for production (Cache Components on) and runs both projects (`phone`, `desktop`), and the build does not stop with `SecurityFatalError`. If a failure needs more than the version bump to fix, stop and widen this change as the design's risks describe.
- [x] 2.2 Check `git status` in `frontend/`. Verify: only `package.json`, `package-lock.json` and, if the new `next` regenerated it, `AGENTS.md` changed. Build output (`.next/`, `test-results/`) stays untracked.

## 3. CI

- [x] 3.1 Commit `package.json`, `package-lock.json` (and `AGENTS.md` if changed) together on a branch, push it and open a pull request. Verify: the CI `frontend` job (`npm ci`, lint, typecheck, Playwright) and the `backend` job are green on the pull request.
