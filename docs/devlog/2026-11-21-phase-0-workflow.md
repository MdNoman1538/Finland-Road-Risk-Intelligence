# 2026-11-21 — Phase 0 kickoff: development workflow

## Goal of the session

Start Phase 0 with an industry-standard development process: tested, maintainable, every change reviewed through a pull request.

## Question asked first: is our process industry practice?

An honest review of our process so far:
- **Matches common industry practice:** ADRs, measure-before-optimise, tests/CI before features, keeping non-deterministic components out of safety decisions, eval-driven LLM work.
- **Not a team convention:** the devlog. Teams usually record reasoning in PRs, issues and design docs. We keep the devlog because it serves learning and the portfolio, but we don't claim it is industry standard.
- **Missing:**
  1. agent instructions kept in the repo
  2. branches + PRs + review
  3. an issue tracker
  4. test-first bug fixes

The owner accepted all four.

## Decisions

[ADR-0004](../decisions/0004-development-workflow.md): GitHub Flow, Conventional Commits, small single-purpose PRs, squash merge, test-first fixes, Definition of Done including docs, branch protection with CI required.

Trade-offs considered:
- **Git Flow:** too heavy for one developer deploying continuously.
- **Trunk-based:** needs a strong test suite we don't have yet.
- **Required approvals:** set to 0, because GitHub won't let authors approve their own PRs. Human review is enforced by the process and the PR checklist instead.

## Why agent rules moved from local memory into `CLAUDE.md`

Until now, rules such as "update the docs every session" lived in the AI agent's memory on one laptop. That memory is invisible to other tools and collaborators, isn't versioned, and can't be reviewed. Putting the rules in the repo makes them part of the codebase: reviewed in PRs, with a history.

## What was built (PR 1, branch `docs/project-documentation-and-workflow`)

- `CONTRIBUTING.md`: the human workflow
- `CLAUDE.md`: rules for AI agents, design rules, codebase map, data facts
- `.github/pull_request_template.md`: with the Definition of Done checklist
- `.github/ISSUE_TEMPLATE/`: bug report and task templates
- ADR-0004, plus updates to the roadmap, status and README
- The `docs/` folder from the planning session (first commit of it)

## Ordering problem noticed

Branch protection can only *require* CI checks once a CI workflow exists and has run. So the order is:
1. this PR
2. the tooling/CI PR
3. switch on protection
4. the bug-fix PR, which will then be the first one gated by CI

## PR 2: tooling and CI (branch `chore/tooling-and-ci`, stacked on PR 1)

### What was built
- **`pyproject.toml` + `uv.lock`.** One source of truth for dependencies and tool config. `uv` resolves and pins all 70 packages.
- **`requirements.txt` is now generated** (`uv export`), because Render installs with pip. A pre-commit hook regenerates it, and CI fails if it drifts from the lock. The old file had only `>=` lower bounds, so every Render build could get different versions. Now local, CI and Render get the same ones.
- **ruff** (lint and format): rules E, F, W, I, B, UP, SIM; line length 110; E501 ignored because the formatter owns line length.
- **pytest:** 36 unit tests to start (translations, tier boundaries, input validation, API contract). None of them needs the spatial extension.
- **pre-commit hooks:** `no-commit-to-branch` enforces the workflow locally; also blocks large files, detects private keys, runs ruff, and keeps the lock and export in sync.
- **GitHub Actions CI:**
  - two jobs: lint/dependency checks, and tests
  - read-only permissions; cancels runs made outdated by a newer push
  - actions pinned to exact versions found with `git ls-remote`, not guessed

### Surprises and lessons
1. **The Render bug reproduced itself on our machine.** `uv` resolved DuckDB **2.0.1** (the conda env has 2.0.0). DuckDB stores extensions per version (`~/.duckdb/extensions/v2.0.1/`), so `LOAD spatial` failed exactly as on Render. Any DuckDB upgrade triggers the bug, not only a fresh server. More evidence for the fix in PR 3.
2. **Checked that formatting didn't change behaviour.** We ran the engine on Oulu (250 m) and Helsinki (2 km) before and after the mechanical formatting commit. Outputs were identical (95 / 57.8 / HIGH and 4659 / 50.9 / HIGH).
3. **`.git-blame-ignore-revs` was tried and dropped.** It lists bulk-formatting commits for `git blame` to skip. But we squash-merge, so the formatting commit's SHA disappears at merge time. The squashed commit also contains real changes, so ignoring it would hide them. For ~1,200 lines of code it isn't worth a separate PR. Recorded so we don't try it again without a reason.
4. **The format check caught our own new test file on the first run.** Expected; the tooling works.
5. **The silent `try/except: pass` around `INSTALL spatial`** in the dashboard is marked `noqa` with a pointer to the known issue, rather than "fixed" with `contextlib.suppress`, which would hide the problem behind tidier syntax. PR 3 removes it.

### Follow-ups noted
- Starlette warns that using `httpx` with its test client is deprecated. Check the recommended replacement when FastAPI's TestClient updates.
- Pin GitHub Actions to commit SHAs instead of tags (supply-chain hardening), probably in Phase 10.
- The package is literally named `src` (`from src.scoring import …`). That's unusual, but renaming is a larger refactor, deferred.

## Next

1. Push PRs 1 and 2 and switch on branch protection once CI has run.
2. PR 3: test-first fix for the spatial extension, persistent connection, and a health check that actually exercises the database.
