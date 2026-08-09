# Agent entrypoint

Use `SKILL.md` as the authoritative workflow and read only the referenced files needed for the current stage.

1. On a fresh clone, install the browser dependency with `npm install` unless a compatible Playwright runtime is already exposed, then run once: `python -X utf8 scripts/bootstrap.py --node <node-path>`. After a fingerprint change, rerun bootstrap. Do not run the full suite per session or per company.
2. Before a normal report, run `python -X utf8 scripts/doctor.py --node <node-path>`; then use `scripts/run_report_pipeline.py`.
3. Default output is HTML. Generate PDF or Word only when requested.
4. Policy currentness is always checked live against official sources. Reuse URLs and within-run results, never cached final eligibility conclusions.
5. Do not silently degrade when browser, network, Playwright, policy evidence or validation is unavailable. Stop with the exact missing capability.
6. Keep complete evidence, policy conditions and exclusions in ledgers; keep the report policy table to `匹配政策或工具 | 匹配原因`.
