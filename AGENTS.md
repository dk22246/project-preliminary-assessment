`SKILL.md` is the business authority. Deploy the complete Skill directory at one fixed Git commit; do not copy individual scripts or examples.

## Public workflow

Agents and users must invoke only `scripts/ppa.py`. All other scripts are internal implementation and must not be called as a parallel workflow.

```powershell
# Run once after first install or a Skill version change.
& <python-path> -X utf8 scripts/ppa.py setup [--with-word]

# Create one clean enterprise workspace.
& <python-path> -X utf8 scripts/ppa.py start "企业法律全称" --work-dir work/company

# After writing entity and listing route in enterprise-findings.json, obtain the minimum route-specific research plan.
& <python-path> -X utf8 scripts/ppa.py research-plan --work-dir work/company

# Fill enterprise-findings.json and policy-findings.json, then compile once and run one final gate.
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
& <python-path> -X utf8 scripts/ppa.py discover-policies --work-dir work/company
```

## Non-negotiable execution rules

- `setup` is deployment-only. Daily report runs must not reinstall dependencies, redownload Chromium, or run the release suite.
- `start` creates two editable inputs, five generated ledgers, and `workflow-state.json`. Never use an example company as a new report workspace.
- Entity and listing route are written in `enterprise-findings.json`. Generate and follow only that route's `research-plan.json`; never run both listed and nonlisted research paths.
- Researchers edit only `enterprise-findings.json` and `policy-findings.json`. `compile` owns the five formal ledgers and replaces them atomically; do not hand-maintain generated ledgers.
- `discover-policies` reuses one real-time official-source scan per department and entry, merges the machine receipt into `policy-findings.json`, and never overwrites human eligibility judgments. Complete only unresolved paths.
- Policy conclusions still require current official text, validity, territory, application or processing state, conditions, and a traceable enterprise path. A failed page fetch is not “no policy”.
- `finalize` is the only complete semantic validation gate and runs once after inputs are complete. `advance` exists only as a compatibility alias for `finalize`.
- `deliver` accepts only the same workspace's current generated ledgers and `report_ready` receipt. After either editable input changes, rerun `compile` and `finalize` before delivery.
- Missing facts must be reported as gaps. Never invent enterprise facts, policies, shareholder percentages, financial values, or eligibility.
