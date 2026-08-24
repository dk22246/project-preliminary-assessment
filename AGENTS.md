`SKILL.md` is the sole authority; deploy only by fully cloning or copying the complete Skill directory.

## Required workflow

- If no compatible Playwright runtime is already available, run `npm install` in the Skill root before bootstrap.
- On first deployment or fingerprint change, run:
  `python -X utf8 scripts/bootstrap.py --node <node-path>`
- For every normal task, first run:
  `python -X utf8 scripts/doctor.py --node <node-path>`
- Then run:
  `python -X utf8 scripts/run_report_pipeline.py <report-data.json> --equity-evidence <equity-evidence.json> --research-ledger <research-ledger.json> --policy-search-ledger <policy-search-ledger.json> --out-dir <output-dir> --node <node-path>`
- Deliver HTML by default; generate PDF or Word only when requested.
- For every report, verify current policy in real time against official sources.
- If required capability, evidence, or validation is unavailable, stop and name the gap; never silently downgrade.
