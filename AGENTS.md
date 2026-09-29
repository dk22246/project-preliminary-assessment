`SKILL.md` is the business authority. Deploy the complete Skill directory at one fixed Git commit; do not copy individual scripts or maintenance fixtures.

## Public workflow

Agents and users must invoke only `scripts/ppa.py`. All other scripts are internal implementation and must not be called as a parallel workflow.

```powershell
# Run once after first install or dependency changes; validates browser availability, not release tests.
& <python-path> -X utf8 scripts/ppa.py setup

# Create one clean enterprise workspace.
& <python-path> -X utf8 scripts/ppa.py start "企业法律全称" --work-dir work/company

# After writing entity and listing route in enterprise-findings.json.research.enterprise_profile, obtain the minimum route-specific research plan.
& <python-path> -X utf8 scripts/ppa.py research-plan --work-dir work/company

# Complete the enterprise input, then prepare the enterprise stage without policy dependency.
& <python-path> -X utf8 scripts/ppa.py prepare-enterprise --work-dir work/company
# Discover real official receipts and draft candidates; then fill policy-findings.json.
& <python-path> -X utf8 scripts/ppa.py discover-policies --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py compile --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py finalize --work-dir work/company

# Deliver only after report_ready. HTML is default; PDF and Word are optional.
& <python-path> -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company [--pdf] [--word]
```

Optional evidence and search commands remain behind the same entrypoint:

```powershell
& <python-path> -X utf8 scripts/ppa.py status --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py collect-web "企业" "主题" --url <official-url> --out-dir work/company/evidence/topic
& <python-path> -X utf8 scripts/ppa.py collect-equity "企业法律全称" --provider qcc-web --input-json capture.json --out-dir work/company/evidence/qcc
& <python-path> -X utf8 scripts/ppa.py search-catalog "业务关键词" --subject-type domestic
```

## Non-negotiable execution rules

- When the user requests Skill maintenance, an Agent may read and edit any tracked source, instruction, reference, schema, template, or test file needed for that maintenance. The input restrictions below apply only while producing an enterprise report; they are not a repository read-only policy.
- `setup` is deployment-only. Daily report runs must not reinstall dependencies, redownload Chromium, or run the release suite.
- `start` creates two editable inputs, five generated ledgers, and `workflow-state.json`. Never use `tests/fixtures` as a new report workspace. Fixture data is maintenance-only and every public renderer must reject it unless an internal release test explicitly enables fixture mode.
- Entity and listing route are written in `enterprise-findings.json.research.enterprise_profile`. Generate and follow only that route's `research-plan.json`; never run both listed and nonlisted research paths.
- `prepare-enterprise` is independent of policy input and reaches `landing_businesses_complete` after the enterprise three-ledger and landing checks.
- The catalog stage reads the existing Excel plus same-source JSON as the single built-in library; the matching stage references `catalog_entry_id` and zero-based `detail_index` (one detail may default to `0`; multiple details require an explicit choice), then later steps reference the derived result. AI judges business activity and technical conditions. Preserve version and official provenance; the local library is not proof of current policy validity, and official changes only prompt an update rather than an evidence-free edit.
- Top-level `equity` and `policy_records` are the sole judgment records; report views and formal ledgers are compiler-derived. Stable equity node keys and edge references, policy source/search/fact/landing keys, conditions, qualification, disposition, handling and report group must not be duplicated by hand.
- Researchers edit only `enterprise-findings.json` and `policy-findings.json`. `compile` owns the five formal ledgers and replaces them atomically; do not hand-maintain generated ledgers.
- `discover-policies` reuses one real-time official-source scan per department and entry, may scan bounded official links,正文 and attachments, and merges real receipts and draft candidates without establishing eligibility. It never overwrites human judgments; complete only unresolved paths. Preserve unchanged completed records; changed or newly failed evidence is pending review.
- Policy conclusions still require current official text, validity, territory, application or processing state, conditions, and a traceable enterprise path. A failed page fetch is not “no policy”.
- `finalize` is the sole complete semantic validation entry and reports independent errors together. On failure, correct the editable inputs, recompile, and rerun finalize; a failed attempt is not a reason to abandon repair. Do not rerun maintenance release tests during report work. Only an all-clear run writes `report_ready` and the final hash. `advance` is a compatibility alias.
- `deliver` accepts only the same workspace's current generated ledgers and `report_ready` receipt. After either editable input changes, rerun `compile` and `finalize` before delivery.
- Missing facts must be reported as gaps. Never invent enterprise facts, policies, shareholder percentages, financial values, or eligibility.
- Legacy input is accepted only through `migrate-findings --work-dir <work-dir>`; conflicts must stop. For a compatible Skill update, run `ppa.py resume --work-dir <work-dir>` to preserve inputs/evidence, then prepare/compile/finalize under current rules. Never manually rewrite fingerprints, dates, or passed receipts.
- Report production uses one stable installed version. Code repair and release tests belong to maintenance. Subtasks deliver sourced findings and explicit gaps; they do not independently rerun the full report workflow.
- Same-run official evidence is shared between collect-web and discovery for up to 24 hours with its original capture time. New runs and stale evidence require a fresh official request.
