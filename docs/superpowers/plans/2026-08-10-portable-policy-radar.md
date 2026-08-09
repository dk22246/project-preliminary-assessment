# Portable Policy Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将股权闭合、专业行业定位、两列政策机会表和跨 Agent 可移植运行固化为可验证的 Skill 契约。

**Architecture:** `report-data.json` 仍是报告唯一事实源；后台 `research-ledger.json`、`policy-search-ledger.json` 和 `equity-evidence.json` 保留完整证据与条件，前台只呈现对招商人员有价值的压缩结果。部署层新增平台无关的 Python 自检与版本指纹，使完整验证仅在安装或版本变化时运行，正常报告只做快速能力检查。

**Tech Stack:** Python 标准库、JSON Schema 风格校验、HTML/CSS/SVG、Node.js/Playwright、可选 python-docx。

---

### Task 1: 固化回归契约

**Files:**
- Create: `tests/test_policy_opportunity_report_contract.py`
- Modify: `tests/test_equity_chart.py`
- Create: `tests/test_portable_bootstrap.py`

- [ ] 写测试，要求股权图显示剩余股东比例且合计闭合到 100%。
- [ ] 写测试，要求正式报告政策表仅有“匹配政策或工具、匹配原因”两列。
- [ ] 写测试，要求行业地位使用“排名/份额/第一梯队”证据化表达。
- [ ] 写测试，要求海外业务信号在后台逐项处置 ODI、EF、跨境结算、境外所得、资金池和离岸贸易等相邻工具。
- [ ] 写测试，要求部署验证按版本指纹复用，版本未变时不重复运行完整验证。
- [ ] 运行上述定向测试并确认因缺少新行为而失败。

### Task 2: 修改数据契约与渲染

**Files:**
- Modify: `schemas/report.schema.json`
- Modify: `scripts/report_core.py`
- Modify: `scripts/render_equity_chart.py`
- Modify: `scripts/render_report_html.py`
- Modify: `scripts/render_report_word.py`
- Modify: `references/report-template.md`
- Modify: `references/equity-evidence.md`

- [ ] 增加行业地位结构化字段和专业表达校验。
- [ ] 增加股权比例闭合校验与“其他股东合计”节点规则，禁止重复计算。
- [ ] 将股权来源摘要压缩为“来源文件 + 编号 + 数据时点”，冲突仅在真实存在时展开。
- [ ] 将 HTML/Word 政策表统一改为两列，来源链接嵌入政策标题或参考资料。

### Task 3: 建立动态政策机会雷达

**Files:**
- Modify: `SKILL.md`
- Modify: `references/business-discovery.md`
- Modify: `references/policy-discovery.md`
- Modify: `references/policy-search-coverage.md`
- Modify: `references/policy-scope.md`
- Modify: `scripts/validate_policy_search_coverage.py`
- Modify: `scripts/validate_business_policy_ledger.py`

- [ ] 将“明确拟落地业务才检索”扩展为“企业事实信号—相邻经营活动—政策或工具机会”。
- [ ] 要求每个观察到的事实信号在后台获得纳入、合并、排除、失效或待核处置，不得静默消失。
- [ ] 固化海外业务信号的动态扩展主题，但明确它们是发现路由而非固定可享受政策清单。
- [ ] 仅允许正式现行且有企业事实支撑的正向机会进入两列前台表。

### Task 4: 跨 Agent 部署与性能收口

**Files:**
- Create: `scripts/runtime_state.py`
- Create: `scripts/bootstrap.py`
- Create: `scripts/doctor.py`
- Modify: `scripts/verify_skill.py`
- Modify: `scripts/run_report_pipeline.py`
- Create: `AGENTS.md`
- Create: `runtime-requirements.json`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `agents/openai.yaml`

- [ ] 自动发现 Python、Node、Chrome、Playwright 与可选 Word 能力并生成本地版本化状态文件。
- [ ] 版本未变化时只运行快速 doctor；版本变化或首次安装时才执行部署验证。
- [ ] 正常流水线启动时快速失败并明确缺失能力，不允许静默降级。
- [ ] 将实时政策结论保持为每次运行实时核验，只复用同轮检索结果和官方入口注册表。

### Task 5: 飞科案例与一次性最终验收

**Files:**
- Modify: `examples/flyco-report-data.json`
- Modify: `examples/flyco-equity-evidence.json`
- Modify: `examples/flyco-research-ledger.json`
- Modify: `examples/flyco-policy-search-ledger.json`

- [ ] 实时核验 2026 年相关政策原文与现行状态，失效政策只留后台处置。
- [ ] 更新飞科股权闭合、行业地位和海外业务政策机会。
- [ ] 在干净克隆中运行 bootstrap，并仅执行一次飞科完整流水线验收。
- [ ] 检查 HTML 两列表格、股权 100% 闭合、文本不重叠和来源链接。
- [ ] 提交全部目标文件并推送 `codex/portable-policy-radar`。
