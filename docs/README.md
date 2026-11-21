# Project Documentation

This folder is the living record of the project: **what** we built, **why** we built it that way, and **how our thinking changed** along the way. It is updated continuously as development happens, not written once at the end.

## Map of this folder

| Path | What it holds | When it is updated |
|---|---|---|
| [project-status.md](project-status.md) | Snapshot of what exists today, measured against the roadmap. Gaps, known issues, performance baseline. | At the end of every phase, and whenever something significant changes |
| [roadmap.md](roadmap.md) | The phased plan from today's dashboard to an in-car alert system. Goals, architecture, phase-by-phase scope and exit criteria. | When a phase is re-scoped or completed |
| [decisions/](decisions/) | **Architecture Decision Records (ADRs)**: one file per significant decision, with the context, the options considered, and the consequences. | Every time we make a decision that would be expensive to reverse or that someone will later ask "why?" about |
| [devlog/](devlog/) | **Development log**: one entry per working session. What we did, what we found, what surprised us, what we decided and why, and what is next. | Every working session |

## How to read it

- New to the project? Read [roadmap.md](roadmap.md), then [project-status.md](project-status.md).
- Want to know why something is the way it is? Look in [decisions/](decisions/).
- Want the story of how it evolved? Read [devlog/](devlog/) in date order.

## Conventions

**ADRs** (decision records)
- File name: `NNNN-short-title.md`, numbered in order and never renumbered.
- Status is one of: `Proposed`, `Accepted`, `Superseded by NNNN`, `Deprecated`.
- An accepted ADR is never edited to change its decision. If we change our minds, we write a new ADR that supersedes it. The history of reasoning is the point.
- Use [decisions/template.md](decisions/template.md).

**Devlog**
- File name: `YYYY-MM-DD-short-topic.md`.
- Write down the reasoning, not just the result: what we expected, what the data actually showed, and dead ends included.
- Numbers must come from a measurement we actually ran. Say how it was measured.

**Status file**
- Always carries an "as of" date.
- Every claim about the code or data should be verifiable (file reference, query, or benchmark).
