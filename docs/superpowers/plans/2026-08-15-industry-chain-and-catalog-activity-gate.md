# Industry Chain and Catalog Activity Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved industry-chain presentation, sales-channel wording, and deterministic activity-level encouraged-industry gate without slowing normal report runs.

**Architecture:** Replace free-text report fields with validated structures. Keep catalog discovery as recall, add deterministic catalog-entry classification and activity compatibility checks before rendering, then render the same validated JSON to HTML and Word.

**Tech Stack:** Python 3, JSON Schema, unittest, HTML/CSS, python-docx.

---

### Task 1: Lock the new report contract with failing tests

**Files:**
- Create: `tests/test_industry_chain_and_activity_gate.py`
- Modify: `tests/test_report_structure_simplification.py`

- [ ] Add tests requiring `sales_channels`, structured `industry_chain`, three ordered stages, source-backed representative enterprises, and activity-level catalog assessments.
- [ ] Add a regression test showing coal sales cannot be a direct match for coal mining/development entries and missing hard conditions can only be potential.
- [ ] Run the focused tests and confirm they fail because the new fields and validator behavior do not exist.

### Task 2: Implement the structured data and deterministic gate

**Files:**
- Modify: `schemas/report.schema.json`
- Modify: `scripts/report_core.py`
- Modify: `scripts/search_industry_catalog.py`
- Modify: `scripts/validate_encouraged_industry_assessment.py`
- Modify: `references/encouraged-industry-assessment.md`
- Modify: `references/business-decomposition.md`
- Modify: `SKILL.md`

- [ ] Add fixed activity types and catalog-entry classifications.
- [ ] Derive the catalog classification from packaged entry text and reject agent-provided drift.
- [ ] Require activity coverage per business and enforce direct/potential/no-match boundaries.
- [ ] Run the focused validator tests and confirm they pass.

### Task 3: Render the approved report structure

**Files:**
- Modify: `references/report-template.md`
- Modify: `scripts/render_report_html.py`
- Modify: `scripts/render_report_word.py`
- Modify: `examples/flyco-report-data.json`

- [ ] Rename the business-table column and data field to sales channels.
- [ ] Render the three-stage industry chain with representative enterprises embedded in each stage and no relationship table.
- [ ] Render activity-level catalog rows.
- [ ] Update the example with source-backed structured values.
- [ ] Run the focused rendering tests and confirm they pass.

### Task 4: Final consistency, release and upload

**Files:**
- Modify only if required by verified failures: packaging contracts and tests directly related to the three changes.

- [ ] Run `scripts/verify_skill.py --release --smoke` once with bundled Python and Node.
- [ ] Inspect the generated HTML and confirm layout checks pass.
- [ ] Review `git diff`, stage only files from this plan, commit, and push to the configured GitHub remote.

