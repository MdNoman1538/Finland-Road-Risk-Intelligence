# Contributing

How work gets done in this repository. It applies to every contributor: humans and AI coding agents alike (agents also read [CLAUDE.md](CLAUDE.md)). The reasoning behind this process is in [ADR-0004](docs/decisions/0004-development-workflow.md).

## The workflow: GitHub Flow

`main` is always working and deployable. Every change, however small, goes through a pull request.

```
1. Issue        Describe the task or bug (use the issue templates).
2. Branch       git switch -c <type>/<short-description>   (from an up-to-date main)
3. Test first   For bugs, write a test that FAILS because of the bug.
4. Code         Smallest change that makes the tests pass.
5. Check        Lint + tests pass locally (see "Local checks").
6. Commit       Conventional Commit messages (see below).
7. Push + PR    Fill in the PR template; link the issue ("Closes #12").
8. CI           GitHub Actions must be green.
9. Review       A human reads every line, especially AI-written code.
10. Merge       Squash merge; delete the branch.
```

## Branch names

`<type>/<short-kebab-description>`, using the same types as commits, for example:
`fix/spatial-extension-install`, `feat/sun-position-module`, `docs/adr-tile-format`, `chore/ci-setup`.

## Commit messages: Conventional Commits

```
<type>(<optional scope>): <imperative summary, max ~72 chars>

<optional body: WHY the change was made, not just what>
```

| Type | Use for |
|---|---|
| `feat` | New user-visible capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding or fixing tests only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `chore` | Tooling, dependencies, config |
| `ci` | CI pipeline changes |
| `data` | Ingestion / schema / data-quality changes |

Example: `fix(scoring): install spatial extension before loading it`

## Pull requests

- **One purpose per PR.** If the description needs "and also…", split it.
- **Small:** aim for under ~400 changed lines of code (data files and lockfiles excluded).
- Fill in the [PR template](.github/pull_request_template.md) completely.
- Merging is done with **squash merge**, so the PR title must be a valid Conventional Commit message.

## Definition of Done

A change is done only when **all** of these are true:

- [ ] Tests cover the change; for a bug fix, a test that failed before the fix now passes.
- [ ] Lint and tests pass locally, and CI is green.
- [ ] Docs are updated:
  - a [devlog](docs/devlog/) entry for the session
  - an [ADR](docs/decisions/) for any significant or hard-to-reverse decision
  - [project-status.md](docs/project-status.md) if status, issues or measurements changed
- [ ] Every performance or data claim comes from a measurement that was actually run, and says how.
- [ ] No secrets, credentials or personal data in the diff.
- [ ] A human has reviewed the full diff.

## Working with AI coding agents

AI agents speed up the work, but accountability stays with the human. The rules:

1. **Plan before code.** For anything non-trivial, the agent states its plan first; the human agrees to the approach.
2. **Tests are the contract.** Agent-written code is trusted only as far as the tests verify it.
3. **Review every diff.** Never merge code you haven't read and understood. If you don't understand it, ask for an explanation. That is part of learning, not a delay.
4. **The agent follows this document** and the project rules in [CLAUDE.md](CLAUDE.md).

## Setup (once)

```bash
# Requires uv: https://docs.astral.sh/uv/  (brew install uv)
uv sync                          # creates .venv with exact locked versions (incl. dev tools)
uv run pre-commit install        # run checks automatically on every commit
```

## Local checks

These are the same checks CI runs ([.github/workflows/ci.yml](.github/workflows/ci.yml)):

```bash
uv run ruff check .              # lint
uv run ruff format .             # auto-format (CI runs: ruff format --check .)
uv run pytest                    # tests
uv run pre-commit run --all-files   # every hook on every file
```

The pre-commit hooks also:
- **refuse commits on `main`**
- block files over 1 MB
- detect private keys
- keep `uv.lock` and `requirements.txt` in sync with `pyproject.toml`

## Dependencies

- Add or remove a dependency with `uv add <pkg>` / `uv remove <pkg>` (dev tools: `uv add --dev <pkg>`). Never edit `requirements.txt` by hand.
- `pyproject.toml` declares what we depend on, and `uv.lock` pins the exact versions.
- `requirements.txt` is **generated** from the lock, because Render installs with pip. The pre-commit hook regenerates it, and CI fails if it drifts.
