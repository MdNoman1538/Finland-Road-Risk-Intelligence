# 2026-11-22: Merging the Phase 0 stack, protecting main, hiding internal errors

## Merging a stack of PRs

PRs #1–#4 were *stacked*: each one's base was the previous branch, not `main`. They were merged in order. After each merge, the next PR's base was switched to `main` (`gh pr edit N --base main`), and it was merged only after its CI was green. All four used **merge commits** rather than squash, so each commit's `Changes:` note survives on `main` for projectViewer to show. The same reasoning is in projectViewer's ADR-0007.

**Why the order matters:** if #1 had been squash-merged, #2's branch would still contain #1's original commits. GitHub would then show them again as "new" in #2, and they could conflict with the squashed copy. Merge commits avoid this, because the original commits stay part of `main`'s history.

PR #1 had no CI run, because the CI workflow itself only arrives in #2.

## Branch protection

`main` now requires a PR, plus the checks **Lint & dependency checks** and **Tests**, with "branch must be up to date" (`strict`) turned on.
- **Required approvals is 0:** GitHub doesn't let the author approve their own PR. Human review is enforced by the process instead (ADR-0004).
- **Why `strict`:** two PRs can each pass CI alone and still break `main` once combined. Requiring the branch to be up to date makes CI run on the combined result.

## Known issue #10: internal errors leaked to clients

**Test first.** A new test points the engine at a database file that doesn't exist, then calls all three risk endpoints. Before the fix, the POST endpoint's 500 response contained the **full filesystem path** of the database, copied from DuckDB's error text through `HTTPException(detail=str(exc))`. The GET and route endpoints had no handler at all.

**Fix.** One app-wide `@app.exception_handler(Exception)`:
- **Server log:** the full traceback, under a random 12-character `error_id`.
- **Client:** only `{"detail": "Internal server error", "error_id": "…"}`.

This is the standard pattern (OWASP, "Improper Error Handling"):
- **The operator** still gets everything needed to debug.
- **The user** gets an id to quote in a bug report.
- **An attacker** learns nothing about paths, SQL or library versions.

Deliberate choices:
- **One handler instead of try/except in each endpoint.** New endpoints are covered automatically, and a forgotten `try` can't reintroduce the leak.
- **`exc_info=exc` passed explicitly** instead of `logger.exception()`. `logger.exception` reads Python's "currently handled exception", and that isn't guaranteed to be set when an async handler runs. A second test checks that the log record really carries the original exception.
- **`HTTPException` (e.g. the 400 for an empty route) is unchanged.** FastAPI handles it before this handler, so deliberate client errors keep their messages.

## Also verified

The projectViewer Claude Code hook now works in real use: edits made in this session appeared live in the viewer's activity feed.
