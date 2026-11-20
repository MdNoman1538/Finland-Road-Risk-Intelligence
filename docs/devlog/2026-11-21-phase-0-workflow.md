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

## Next

PR 2: `pyproject.toml` + `uv`, ruff, pytest, pre-commit, GitHub Actions CI.
