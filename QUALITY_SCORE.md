# Quality Score — navvi

> Maintained by the entropy skill. Do not edit manually.
> Grade scale: A=all signals green, B=1 signal missing, C=2 missing, D=3+, F=no docs

Last audit: 2026-05-18 (weekly sweep — first scan, baseline established)

## Domains

| Domain | Grade | Last audit | Notes |
|--------|-------|------------|-------|
| src | C | 2026-05-18 | S1 ❌ no docs/code-structure.md, S4 ✅ (1 issue), S6 ❌ hookshot not configured. Score 2→C |
| companions | C | 2026-05-18 | S1 ❌, S4 ✅ (0 issues), S6 ❌ hookshot not configured. Score 2→C |
| container | D | 2026-05-18 | S1 ❌, S4 ⚠️ (5 issues — above threshold), S6 ❌ hookshot not configured. Score 2.5→3→D |
| mcp | C | 2026-05-18 | S1 ❌, S4 ✅ (2 issues), S6 ❌ hookshot not configured. Score 2→C |
| scripts | C | 2026-05-18 | S1 ❌, S4 ✅ (0 issues), S6 ❌ hookshot not configured. Score 2→C |
| skills | C | 2026-05-18 | S1 ❌, S4 ✅ (0 issues), S6 ❌ hookshot not configured. Score 2→C |

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

## Per-Domain Signal Details (2026-05-18 sweep)

| Domain | S1 Doc Coverage | S4 Issues | S6 Hookshot | Score | Grade |
|--------|----------------|-----------|-------------|-------|-------|
| src | ❌ | ✅ (1) | ❌ not configured | 2 | C |
| companions | ❌ | ✅ (0) | ❌ not configured | 2 | C |
| container | ❌ | ⚠️ (5) | ❌ not configured | 2+0.5=2.5→3 | D |
| mcp | ❌ | ✅ (2) | ❌ not configured | 2 | C |
| scripts | ❌ | ✅ (0) | ❌ not configured | 2 | C |
| skills | ❌ | ✅ (0) | ❌ not configured | 2 | C |

**S2/S3/S5 skipped** for all domains (see Signal Applicability above).

## Entropy Findings

### First Scan — Baseline Established

This is the initial entropy scan for navvi. No prior grades exist; no regressions or improvements to report.

**Summary:** 5 domains graded C, 1 domain graded D (container).

**Primary gaps — universal across all domains:**
- **S1 absent:** docs/code-structure.md does not exist in this repo. All 6 domains fail this signal automatically.
- **S6 absent:** Hookshot is not configured. All 6 domains fail this signal.

**Recommended fix:** Run `/setup-harness fellowship-dev/navvi` to create docs/code-structure.md, then run `/hookshot` to configure coverage enforcement.

### D-Grade Domain: container

container is the most actively committed domain (recent FastAPI/uvicorn dependency bumps) with no documentation coverage. In addition to the universal S1/S6 gaps, container has 5 open issues (S4 ⚠️ — above the 3-issue threshold), pushing its score to 3 → D.

A GitHub issue has been filed to track remediation.

## History

| Date | Action | Result |
|------|--------|--------|
| 2026-05-18 | weekly sweep (first scan) | 6 domains, baseline established. 1 D (container), 5 C. |
