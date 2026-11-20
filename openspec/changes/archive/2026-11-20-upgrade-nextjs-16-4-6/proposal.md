# Proposal

## Why

`npm audit` in `frontend/` reports a moderate vulnerability in `next` 16.0.0 to 16.4.4, and the frontend pins `next` to 16.4.1. It lists seven advisories: GHSA-mfr8-8qww-v76h, GHSA-vc7v-qv4w-wrv8, GHSA-rhh4-g77r-r9qj, GHSA-vvgp-ww4w-46vf, GHSA-7qx7-33qx-rqx2, GHSA-f3mh-rxg3-f5g2 and GHSA-pc58-hwjq-p385. The app does not use the affected features today: no `'use cache'` or `unstable_cache`, no dynamic route params, no `next/image`, no Edge runtime and no server-side response forwarding. But `cacheComponents` is on, so the first `'use cache'` anyone adds would sit on a vulnerable version. The fix is a patch release.

The vulnerable version also triggers Next's agent upgrade nudge. When an AI coding agent runs `next build` on a version with a known advisory, the build stops on purpose with `SecurityFatalError` and asks for a retry. That also hits `npm run test:e2e`, whose web server runs `npm run build`. CI is not affected, because the nudge skips CI environments.

## What Changes

- Bump `next` from 16.4.1 to 16.4.6 in `frontend/package.json`, still an exact pin.
- Bump `eslint-config-next` from 16.4.1 to 16.4.6, also an exact pin. It depends on `@next/eslint-plugin-next` at its own exact version, so it moves with `next`.
- Refresh `frontend/package-lock.json`. Within the ranges already declared, this also moves the dev-only `typescript-eslint` from 8.71.2 to 8.73.0, which clears the `minimatch` advisory GHSA-g3hv-75wg-m249 that `npm audit` reports through lint tooling.
- No source, config or test changes are expected. `react`/`react-dom` 19.3.0 already satisfy the peer range of `next` 16.4.6.

Business decisions:

- 2026-11-20: The target is `next` 16.4.6. It is both the first fixed version and the current npm `latest`, so "the fix" and "the latest 16.x" are the same release.
- 2026-11-20: Keep exact pins for `next` and `eslint-config-next` instead of switching to `^` ranges. Builds stay reproducible, and every future framework bump stays an explicit, reviewed change.
- 2026-11-20: The upgrade is a hand-made dependency change, not `next upgrade --agent`. The diff stays limited to the two version numbers and the lock file.
- 2026-11-20: Upgrade now even though the app is not exposed today. The cost is a patch bump verified by the existing suites, and it stops the agent nudge from interrupting builds.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This is a dependency-only change with no observable behavior change (API contracts, UI, answers), so the change sets `skip_specs: true`.

## Impact

- `frontend/package.json`: `next` and `eslint-config-next` versions.
- `frontend/package-lock.json`: regenerated.
- `frontend/AGENTS.md`: may be rewritten by `next dev`/`next build` of the new version. If so, the change is committed with the bump.
- No backend, API, UI or CI workflow changes. No new dependencies.
