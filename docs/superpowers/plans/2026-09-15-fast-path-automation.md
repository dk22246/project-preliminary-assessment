# Project Preliminary Assessment Fast-Path Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不降低主体、证据、产业目录、政策地域与时效、股权和版式门禁的前提下，停止由 AI 手工编写五份复杂台账，把常规上市公司 HTML 报告压缩到 6—8 分钟、非上市公司压缩到 8—10 分钟，并将本地结构化、校验和渲染开销控制在约 30 秒内。

**Architecture:** Agent 只维护 `enterprise-findings.json` 和 `policy-findings.json` 两份精简输入；确定性编译器生成现有五份正式台账及全部编号、引用、回执和哈希。上市/非上市研究继续分路，政策继续实时核验，但按“部门＋入口＋路径”去重并按部门角色生成必要回执；过程只做轻量增量检查，交付前执行一次完整验证。

**Tech Stack:** Python 3.10+、JSON/JSON Schema、现有 `ppa.py` 控制器、urllib/HTML 提取器、Playwright/Chromium、unittest、Git。

---

## 保留与删除边界

必须保留：

- 主体确认与上市/非上市分路；
- 法定披露及官方证据优先级；
- 最近三个完整年度财务和政府补助边界；
- 股权证据闭环；
- 产业目录按具体业务行为匹配；
- 海南全省、三亚市、三亚中央商务区地域门禁；
- 政策原文、有效状态、申报状态和业务触发关系；
- HTML 浏览器版式验收；
- 五份正式台账及现有正式校验器，作为机器生成的后台审计产物。

必须停止：

- Agent 手工创建正式编号、回执字段、跨文件引用和 SHA256；
- 每个部门机械执行七条政策路径；
- 同一部门入口因多个业务或主题重复抓取；
- 每推进一个阶段就重复执行已经通过的完整校验；
- 日常报告运行发布级完整测试；
- 上市路由加载非上市细则、HTML交付加载Word/PDF细则等无关上下文；
- 以临时 `build_ledgers.py` 一类企业专用脚本拼装正式台账。

### Task 1: 固化基线并建立真实性能测试

**Files:**
- Create: `tests/test_fast_path_metrics.py`
- Modify: `scripts/run_report_pipeline.py`
- Modify: `scripts/ppa.py`

- [ ] **Step 1: 将当前未提交的既有改动提交为可回滚检查点**

运行：

```powershell
git status --short
git add -A
git commit -m "checkpoint: preserve workflow hardening before fast path"
```

预期：工作树干净，后续每个任务独立提交，旧逻辑可以按提交回滚。

- [ ] **Step 2: 写入失败测试，证明运行指标不能继续写零**

测试使用临时工作区调用指标记录函数，并断言：

```python
self.assertGreaterEqual(metrics["enterprise_research_seconds"], 0)
self.assertGreaterEqual(metrics["policy_discovery_seconds"], 0)
self.assertIn("phase_seconds", metrics)
self.assertEqual(metrics["full_release_tests_run"], False)
```

同时断言日常 `ppa.py start/advance/deliver` 不会调用 `verify_skill.py --release`。

- [ ] **Step 3: 实现统一阶段计时器**

在 `ppa.py` 的状态中写入 `phase_started_at`、`phase_completed_at` 和 `phase_seconds`；`run_report_pipeline.py` 从状态读取真实企业研究和政策检索耗时，不再硬编码为零。安装测试耗时只记录在 `.runtime/verified.json`，不计入报告耗时。

- [ ] **Step 4: 运行专项测试并提交**

运行：

```powershell
python -X utf8 -m unittest tests.test_fast_path_metrics tests.test_runtime_fast_path tests.test_workflow_controller -v
git add scripts/ppa.py scripts/run_report_pipeline.py tests/test_fast_path_metrics.py
git commit -m "perf: record real report phase timings"
```

预期：专项测试全部通过；不运行完整发布测试。

### Task 2: 建立两份精简输入和确定性台账编译器

**Files:**
- Create: `schemas/enterprise-findings.schema.json`
- Create: `schemas/policy-findings.schema.json`
- Create: `scripts/compile_workspace.py`
- Create: `tests/test_compile_workspace.py`
- Modify: `scripts/init_report_workspace.py`
- Modify: `scripts/ppa.py`

- [ ] **Step 1: 为精简输入写失败测试**

`enterprise-findings.json` 只允许 Agent 提交：主体、来源、事实、业务、财务、股权、风险、产业目录判断、落地业务和主管部门路由；`policy-findings.json` 只允许提交：政策标题、官方URL、发文机关、文号、现行状态、申报状态、匹配业务和匹配原因。

测试断言：Agent 输入不要求 `F01`、`PS01`、`receipt_id`、`artifact_sha256` 或跨文件 ID；编译后现有五份正式台账仍满足当前 schema。

- [ ] **Step 2: 实现确定性编号和引用编译**

`compile_workspace.py` 暴露：

```python
def compile_enterprise_findings(findings: dict, workspace: Path) -> dict[str, dict]:
    """Generate report-data, research-ledger and equity-evidence deterministically."""

def compile_policy_findings(findings: dict, workspace: Path) -> dict[str, dict]:
    """Generate policy-search-ledger and policy-evidence with stable IDs and links."""
```

编号按输入顺序确定生成；来源去重键为 `(url, title, retrieved_at)`；业务、部门、政策和证据关系由编译器一次建立。发现缺少必要证据时，错误直接定位到精简输入的业务或政策条目，不再输出几十条重复字段错误。

- [ ] **Step 3: 修改工作区初始化和唯一入口**

`ppa.py start` 新增两份精简输入并继续创建五份后台台账；新增：

```powershell
python -X utf8 scripts/ppa.py compile --work-dir work/company
```

`compile` 先执行精简输入 schema 检查，再原子写入五份正式台账；编译失败不得部分覆盖旧台账。

- [ ] **Step 4: 运行专项测试并提交**

运行：

```powershell
python -X utf8 -m unittest tests.test_compile_workspace tests.test_init_report_workspace tests.test_research_ledger tests.test_equity_evidence -v
git add schemas scripts tests
git commit -m "feat: compile formal ledgers from lean findings"
```

预期：精简输入可编译为当前正式合同；现有五台账门禁不降低。

### Task 3: 将上市与非上市研究变成可执行快路径

**Files:**
- Create: `references/research-route-index.md`
- Modify: `SKILL.md`
- Modify: `references/evidence-intake.md`
- Modify: `references/business-discovery.md`
- Modify: `scripts/ppa.py`
- Create: `tests/test_research_route_fast_path.py`

- [ ] **Step 1: 写入路由级失败测试**

断言上市路由只产生：最新年报集中提取、以前年度定向补缺、企业官网当前变化、监管风险增量四类动作；非上市路由只产生：企业官方、政府经营事实、客户/合作方公告、工商股权、四类风险及一次定向缺口补查。

- [ ] **Step 2: 实现 `ppa.py research-plan`**

命令读取主体和路由，输出最小行动清单：

```powershell
python -X utf8 scripts/ppa.py research-plan --work-dir work/company
```

同一URL只出现一次；同一PDF只需要提取一次；已由法定披露解决的字段不会再产生媒体补查任务。行动完成状态写入精简输入，而不是由 Agent另建研究台账。

- [ ] **Step 3: 精简运行说明并实施渐进加载**

`SKILL.md` 只保留共用流程和路由入口：上市时只读上市段，非上市时只读非上市段；进入产业目录后才读取目录规则，进入政策阶段才读取政策规则，Word/PDF和园区政策均按需加载。

- [ ] **Step 4: 运行专项测试并提交**

运行：

```powershell
python -X utf8 -m unittest tests.test_research_route_fast_path tests.test_research_stop_gate -v
git add SKILL.md references scripts tests
git commit -m "perf: enforce route-specific enterprise research plans"
```

### Task 4: 自动生成角色化政策扫描和实时增量复验

**Files:**
- Create: `references/policy-source-registry.json`
- Modify: `scripts/discover_current_policies.py`
- Modify: `scripts/policy_cache.py`
- Modify: `scripts/validate_policy_search_coverage.py`
- Modify: `scripts/ppa.py`
- Modify: `references/policy-search-coverage.md`
- Create: `tests/test_policy_role_scan_compiler.py`

- [ ] **Step 1: 写入失败测试，禁止七路径回退**

断言：

```python
self.assertEqual(required_paths_for_role("co_issuer"), (
    "theme_search", "department_documents", "normative_documents", "invalidity_catalog"
))
self.assertNotIn("award_publicity", required_paths_for_role("execution_authority"))
self.assertNotIn("document_graph", required_paths_for_role("primary_regulator"))
```

再用两个业务共同路由同一部门，断言只抓取一次部门入口并只生成一个 `department_scan_profile`。

- [ ] **Step 2: 建立机器可读官方来源注册表**

将现有 `policy-scope.md` 中已经确认的海南省级、驻琼执行机构和三亚市级官方入口转成 `policy-source-registry.json`。每项记录部门、角色可用路径、目录URL、动态状态、允许域名和最后核验时间；Markdown继续解释政策边界，但不再承担机器配置。

- [ ] **Step 3: 扩展实时发现器**

`discover_current_policies.py` 按 `(department, entry_url, path)` 去重，按角色只建立必要路径；不同官方域名最多并发4路，同域名1路。复用缓存前必须本轮重新访问目录或政策原文；申报通知、失效目录和公示始终重新获取。候选文件发现后才追溯原文、细则和办理文件。

- [ ] **Step 4: 让机器回执直接进入正式编译输入**

`ppa.py discover-policies` 不再生成无法使用的空草稿。它输出可直接由 `compile_workspace.py` 消费的政策扫描结果；Agent只补充政策适用判断和一句话匹配原因。网页失败、附件缺失和资格未知继续使用现有阻断或条件型状态，不得伪装成“没有政策”。

- [ ] **Step 5: 运行专项测试并提交**

运行：

```powershell
python -X utf8 -m unittest tests.test_policy_role_scan_compiler tests.test_policy_discovery_runtime tests.test_policy_cache tests.test_policy_search_coverage tests.test_policy_evidence -v
git add references scripts tests
git commit -m "perf: deduplicate realtime policy discovery by department role"
```

### Task 5: 合并重复验证并保持一次最终硬门禁

**Files:**
- Modify: `scripts/ppa.py`
- Modify: `scripts/run_report_pipeline.py`
- Modify: `scripts/workflow_state.py`
- Modify: `scripts/preflight.py`
- Create: `tests/test_single_final_gate.py`

- [ ] **Step 1: 写入验证调用次数测试**

使用 mock 记录校验器调用，断言：编译阶段只运行对应增量结构检查；`ppa.py finalize` 对五份台账运行一次完整校验；`deliver` 在哈希未变化时不重复运行相同校验，只执行渲染和浏览器版式验收。

- [ ] **Step 2: 新增 `ppa.py finalize` 并收敛 `advance`**

正式日常路径调整为：

```powershell
ppa.py start
ppa.py research-plan
ppa.py compile
ppa.py discover-policies
ppa.py compile
ppa.py finalize
ppa.py deliver
```

`advance` 仅作为兼容别名调用当前必要动作，不再循环重跑全部门禁。`finalize` 成功后绑定五台账哈希；任一台账变化才使就绪状态失效。

- [ ] **Step 3: 删除日常发布测试和重复校验路径**

`verify_skill.py --release` 只允许 `ppa.py setup` 在首次安装、显式 `--force` 或Skill指纹变化时调用；正式项目命令不得间接触发。`deliver(trusted_workflow=True)` 只检查已绑定哈希并执行渲染、布局、可选PDF/Word。

- [ ] **Step 4: 运行专项测试并提交**

运行：

```powershell
python -X utf8 -m unittest tests.test_single_final_gate tests.test_workflow_controller tests.test_report_pipeline_policy_evidence -v
git add scripts tests
git commit -m "perf: run one final formal validation gate"
```

### Task 6: 清理旧指令、补安装入口并完成一次最终验收

**Files:**
- Modify: `SKILL.md`
- Create: `README.md`
- Modify: `AGENTS.md`
- Modify: `runtime-requirements.json`
- Delete only when no caller remains: obsolete duplicate references and dead compatibility wording
- Test: all existing `tests/`

- [ ] **Step 1: 清理旧七路径和第二套入口**

使用 `rg` 检查并删除以下运行性残留：`每个部门七路径`、直接调用内部校验器、手工填写五台账、复制示例企业、每项目运行发布测试。示例仅保留发布测试夹具用途，不能出现在日常命令中。

- [ ] **Step 2: 添加面向其他Agent的README**

README只写完整克隆、一次性 `setup`、日常唯一命令、可选PDF/Word、UTF-8及故障诊断；不复制Skill业务规则。固定Git commit或release tag部署，避免其他Agent运行旧逻辑。

- [ ] **Step 3: 执行唯一一次完整发布测试**

运行：

```powershell
python -X utf8 -m unittest discover -s tests -v
python -X utf8 scripts/verify_skill.py --release
```

预期：全部测试通过，完整测试在整个改造中仅执行这一次。

- [ ] **Step 4: 运行三个隔离验收案例**

使用上市公司、非上市公司、具有海外业务的上市公司各一个固定测试夹具，验证：

- 有效政策数和证据强度不低于改造前基线；
- 仍阻断外省、海南非三亚区域专属、过期和缺少正式原文的政策；
- 海外业务仍触发外贸、EF账户、跨境人民币/外汇、ODI、境外直接投资所得、资金池和离岸贸易的逐项处置；
- 没有手写正式台账和企业专用构建脚本；
- HTML无文字、表格或股权图越界；
- `run-metrics.json`记录真实阶段耗时。

- [ ] **Step 5: 最终审查、提交并同步GitHub**

运行：

```powershell
git status --short
git diff --check
git log --oneline --decorate -8
git push origin HEAD:main
```

预期：工作树干净、GitHub主分支包含唯一新运行逻辑、其他Agent按README完成一次性部署后直接使用快路径。

## 最终成功标准

- 正式政策仍是本轮实时核验，不因缓存降低时效性；
- 现有五份正式台账仍存在，但全部由程序生成；
- Agent不再编写重复回执、编号、引用关系和哈希；
- 上市/非上市路径真正改变研究动作和加载规则；
- 业务触发政策，不恢复固定政策清单；
- 日常报告不运行完整发布测试；
- 最终只运行一次完整数据门禁和一次浏览器版式验收；
- 运行时间超过目标时，指标能够明确指出是企业研究、政策网络、结构编译还是渲染阶段，而不是继续猜测。
