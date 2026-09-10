`SKILL.md` is the sole authority; deploy only by fully cloning or copying the complete Skill directory.

## Required workflow

- If no compatible Playwright runtime is already available, run `npm install` in the Skill root before bootstrap.
- On first deployment or fingerprint change, run:
  `python -X utf8 scripts/bootstrap.py --node <node-path>`
- For every normal task, first run:
  `python -X utf8 scripts/doctor.py --node <node-path>`
- Start every new enterprise from a blank workspace, never from the Flyco release fixture:
  `python -X utf8 scripts/init_report_workspace.py "<legal-enterprise-name>" --out-dir <work-dir>`
- After entity resolution, populate `research-ledger.json.enterprise_profile` with the confirmed analysis entity and exactly one route: `listed / listed_disclosure` or `nonlisted / nonlisted_public_evidence`. The route changes enterprise evidence sources and stop conditions only; it must not change report structure or policy research.
- Then run:
  `python -X utf8 scripts/run_report_pipeline.py <report-data.json> --equity-evidence <equity-evidence.json> --research-ledger <research-ledger.json> --policy-search-ledger <policy-search-ledger.json> --policy-evidence <policy-evidence.json> --out-dir <output-dir> --node <node-path>`
- Deliver HTML by default; generate PDF or Word only when requested.
- For every report, verify current policy in real time against official sources.
- Populate all five ledgers from the same run. The packaged Flyco files are release fixtures only and require explicit fixture mode.
- Read current 500-ranking years and source contracts from `references/ranking-registry.json`; never hard-code ranking years in an Agent prompt.
- If required capability, evidence, or validation is unavailable, stop and name the gap; never silently downgrade.
