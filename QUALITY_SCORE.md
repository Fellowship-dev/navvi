# Quality Score — navvi

> Maintained by the entropy skill. Do not edit manually.
> Grade scale: A=all signals green, B=1 signal missing, C=2 missing, D=3+, F=no docs

Last audit: 2026-05-19 (daily sweep — all domains stable)

## Domains

| Domain | Grade | Last audit | Notes |
|--------|-------|------------|-------|
| src | C | 2026-05-19 | S1 ❌ no docs/code-structure.md, S4 ✅ (1 issue), S6 ❌ hookshot not configured. Score 2→C. Stable. |
| companions | C | 2026-05-19 | S1 ❌, S4 ✅ (0 issues), S6 ❌ hookshot not configured. Score 2→C. Stable. |
| container | D | 2026-05-19 | S1 ❌, S4 ⚠️ (6 issues — above threshold, up from 5), S6 ❌ hookshot not configured. Score 2.5→3→D. Stable. |
| mcp | C | 2026-05-19 | S1 ❌, S4 ✅ (2 issues), S6 ❌ hookshot not configured. Score 2→C. Stable. |
| scripts | C | 2026-05-19 | S1 ❌, S4 ✅ (0 issues), S6 ❌ hookshot not configured. Score 2→C. Stable. |
| skills | C | 2026-05-19 | S1 ❌, S4 ✅ (0 issues), S6 ❌ hookshot not configured. Score 2→C. Stable. |

## Signal Applicability

| Signal | ID | Applicable | Reason |
|--------|-----|-----------|--------|
| docs/code-structure.md domain coverage | S1 | Yes | File absent — all domains fail this signal |
| FlowChad flow for critical path | S2 | No | HAS_FRONTEND=false (Python only, no Next.js) |
| Code commit vs doc update delta (≤30d) | S3 | No | docs/code-structure.md does not exist — no baseline to compare against |
| Open issues tagged to domain (≤3) | S4 | Yes | GitHub issues available |
| Test coverage report | S5 | No | No coverage report found — skipped |
| Hookshot enforcement | S6 | Yes | Applicable but not yet configured |

**Grade scale:** 0 failing → A · 1 failing → B · 2 failing → C · 3+ failing → D · no docs → F
Yellow signals (⚠️) count as 0.5, rounded up.

## Per-Domain Signal Details (2026-05-19 sweep)

| Domain | S1 Doc Coverage | S4 Issues | S6 Hookshot | Score | Grade |
|--------|----------------|-----------|-------------|-------|-------|
| src | ❌ | ✅ (1) | ❌ not configured | 2 | C |
| companions | ❌ | ✅ (0) | ❌ not configured | 2 | C |
| container | ❌ | ⚠️ (6) | ❌ not configured | 2+0.5=2.5→3 | D |
| mcp | ❌ | ✅ (2) | ❌ not configured | 2 | C |
| scripts | ❌ | ✅ (0) | ❌ not configured | 2 | C |
| skills | ❌ | ✅ (0) | ❌ not configured | 2 | C |

**S2/S3/S5 skipped** for all domains (see Signal Applicability above).

## Entropy Findings — 2026-05-19

### Regressions (grade dropped)
- None.

### Improvements (grade improved)
- None.

### Stable issues
- All 6 domains unchanged from 2026-05-18 baseline. Primary gaps remain: S1 (no docs/code-structure.md) and S6 (hookshot not configured).
- container S4 worsened: 5 → 6 issues (still ⚠️ within 4-6 range, grade D unchanged).

**Action:** Run `/setup-harness fellowship-dev/navvi` to create docs/code-structure.md, then `/hookshot` to configure enforcement. This would clear S1 and S6 for all 6 domains, lifting most C grades to A.

## History

| Date | Action | Result |
|------|--------|--------|
| 2026-05-18 | weekly sweep (first scan) | 6 domains, baseline established. 1 D (container), 5 C. |
| 2026-05-19 | daily sweep | 6 domains scanned, 0 regressions, 0 improvements. container S4 6 issues (up from 5, still ⚠️). |
