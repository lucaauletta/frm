# Agent handoff

## 2026-10-12 — Coordination across computers

- Established `AGENTS.md` instructions to check GitHub at the start of each session and leave a handoff note after changes.
- Starting point: `main` at `15a8751` (`fix: responsive scrubbing and complete reusable preview caches`). The working tree was clean and `origin` was fetched before this documentation update.
- Changes in this update are documentation only; application behavior is unchanged.
- Validation: documentation whitespace check passed. Tests could not run: `python` is unavailable and `python3 -m pytest -q` reports that `pytest` is not installed. No application code was changed.
- Next agent: fetch `origin`, compare branch state, and read this file before starting work. Record future changes and any unfinished work here.
