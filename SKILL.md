---
name: project-preliminary-assessment
description: 对拟招引企业开展三亚中央商务区招商前期尽调、整体落地推演与海南岛内正式政策检索，默认交付 HTML《招商项目整体落地研判报告》，可按需从同源数据转换 PDF 或可编辑 Word。
---

# 项目前期评估

本 Skill 面向三亚中央商务区招商前期决策。它不是固定政策清单工具：先把企业、业务与落地路径研究清楚，再以实际拟落地业务触发海南岛内政策检索。所有结论均区分公开事实、政策条件与招商推演；“整体迁入”仅是推演情景，不得写成既成事实。

## 默认交付

默认只生成 `report-data.json` 驱动的 HTML 报告，HTML 是主阅读版。用户明确需要时，才从这份最终 HTML 转换 PDF，或从同一份数据生成可编辑 Word。不得分别撰写三套内容，也不得以聊天正文代替文件。

## 跨 Agent 部署门禁

- 仅通过 Git 仓库完整克隆或复制整个 Skill 目录，不得只复制 `SKILL.md`、聊天文本或单个脚本。
- 所有文本和结构化数据均为 UTF-8；读入 JSON 时兼容 UTF-8 BOM，写入时明确指定 UTF-8。Windows PowerShell 必须通过 `scripts/run_utf8.ps1` 启动 Python，以同时统一 Python 与终端输出编码；其他终端使用 `python -X utf8`。
- 新 Agent 首次使用前，必须运行部署预检和测试：PowerShell 使用 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_utf8.ps1 scripts\preflight.py --smoke` 及同一启动器的 `-m unittest discover -s tests -v`；其他终端使用 `python -X utf8 scripts/preflight.py --smoke` 和 `python -X utf8 -m unittest discover -s tests -v`。任一失败时不得生成正式报告。
- 必须先形成 `report-data.json`，再运行 `scripts/run_report_pipeline.py`；不得绕过结构化数据、校验器或 HTML 渲染器直接手写报告。
- 以固定 Git commit 部署并记录 commit SHA；升级时重新执行上述部署门禁。PDF 和 Word 继续仅按用户要求生成。

## 核心运行顺序

1. **确认主体。** 用户只给企业名称时，先判断名称是集团、上市公司、品牌还是经营主体。唯一可识别时直接研究；存在同名、集团与上市主体混淆、品牌与主体混淆时，列出 2—4 个明确选项，请用户确认。确认前不得混用信息。
2. **研究企业。** 建立企业主体、股权结构、主要业务与产品、行业竞争位置、代表性上下游、国内外业务、近三年经营数据、政府补助和重大风险的事实卡。范围与来源见 `references/evidence-intake.md`。
3. **拆解招商价值。** 从企业已有业务、组织能力、区域布局中识别可在三亚中央商务区实质运营的业务与管理职能；不得由政策反向虚构业务。
4. **设计落地路径。** 对每项业务写清三亚承接主体、职能、人员、合同、收入、利润、结算或投资路径，以及可形成的税收、贸易、投资、就业、品牌和产业带动。
5. **检索、核验并提炼重点政策。** 按每项拟落地业务对应的主管部门，先检索海南省级和驻琼执行机构，再检索三亚市及园区正式政策。每项业务均须形成动态“业务—政策检索台账”：写明主题、检索部门、结论、正式政策编号或未纳入原因和下一步核实事项。该台账用于后台防遗漏，不直接作为正式报告主体。逐项核验政策原文、地域、现行状态、条件、办理方式和企业承接路径后，按“企业整体在三亚实质落地”的招商情景，将同一项优惠的政策原文和执行公告合并为一条重点政策，使用业务语言说明实际价值；规则见 `references/policy-scope.md`。
6. **汇总成唯一事实源。** 将确认结果写入符合 `schemas/report.schema.json` 的 `report-data.json`。先运行数据、文本、业务—政策检索台账与政策范围校验，再渲染输出。
7. **生成并复核交付物。** 运行 `scripts/run_report_pipeline.py` 默认生成 HTML；仅在用户要求时附加 `--pdf` 或 `--word`。PDF 和 Word 均须复核文件结构、文字、目录、图表、表格和来源。

## 企业与落地业务判断

- 研究主体关系：集团、上市公司、品牌、子品牌、子公司、控股股东与最终控制方。股权关系仅按已核验的上下级关系绘制，不用文字框堆叠。
- 业务拆分必须覆盖主要业务板块、主要产品、主要承载主体、客户/收入来源、国内外业务布局和三亚潜在结合点。相关方法见 `references/business-decomposition.md`。
- 重资产制造、矿业、农业企业不得机械假设产线迁入。优先判断总部、贸易、投资、结算、品牌、渠道与供应链管理；生产迁入须有产线、用地、物流、环保、能耗和人员事实依据。
- “最适合落地”不是泛泛描述。每项必须说明企业事实基础、可分离性、中央商务区实质运营条件及实际贡献路径。

## 政策硬规则

- 可享受政策仅限海南全省、三亚市或三亚中央商务区的正式、现行文件；国家政策仅作制度背景。外省、海南省内非三亚区域专属、征求意见稿、过期文件和新闻解读不得写成可享受权益。
- 不设企业所得税、个人所得税、EF 账户、ODI、总部认定等固定覆盖清单。仅当企业的拟落地业务触发相应主题时检索；例如迁入总部与人员才检索总部、企业所得税与人才个税，跨境贸易才检索 EF 账户、跨境人民币和外贸，境外投资才检索 ODI 与境外所得政策。
- 不得因业务事实不足而静默省略政策主题。每项拟落地业务的检索结果必须归入“可适用（条件待核）”“条件型政策机会”“暂未触发”或“未发现现行政策”之一；后两类必须写明原因和下一步需向企业核实的事实。该结论留在后台台账和招商工作底稿，不默认作为报告中的“待核政策事项”展示。
- 每条政策先用一句话说明“企业开展什么业务或达到什么条件后，可以获得什么税收优惠、资金支持、办理便利或账户功能”，再写匹配逻辑、条件、办理方式和实际价值。
- 正式报告默认采用整体落地情景：企业在三亚设立并实质运营主体，承接报告已确定的总部管理、品牌、贸易、结算、投资或行业功能。报告聚焦对招商谈判有直接价值的重点政策，不把“条件型政策机会”作为表格中的结论标签；改为在“享受前提及三亚承接”列写清条件。
- 同一项优惠的基础政策、实施细则、认定公告或申报口径不得拆成重复行；合并为一行并在政策依据中并列官方原文。政策名称须先说清企业能得到什么：例如“高端紧缺人才个人所得税优惠（实际税负15%封顶）”“EF账户（多功能自由贸易账户）”，不得只堆砌文件标题。
- 拟写入报告的政策卡必须通过 `scripts/validate_policy_scope.py`；全部业务检索结论必须通过 `scripts/validate_business_policy_ledger.py`。前者是政策正式性、地域、状态与企业承接路径门槛，后者防止业务或政策主题遗漏；二者均不代表企业已取得资格。

## 固定报告结构

严格使用 `references/report-template.md` 的八个一级部分：

1. 项目整体判断
2. 企业基本情况（主体认定、股权架构、业务及产品、行业竞争、上下游及国内外业务）
3. 近三年经营数据（经营表、政府补助明细与分析）
4. 风险与合规情况
5. 三亚落地业务及落地方式
6. 企业政策匹配
7. 综合评估
8. 参考资料

报告内的来源均用 `E/F/R/P` 编号回溯。风险事项少时可用简明文字，不得为了形式制造空表。关键事实、数字、政策和风险必须有可定位来源。

## 文件与执行入口

- `references/entity-resolution.md`：主体确认与股权核验。
- `references/evidence-intake.md`：企业、财务、风险公开信息来源和禁用来源。
- `references/business-decomposition.md`：业务拆分和落地业务筛选。
- `references/policy-scope.md`：官方政策来源、搜索顺序、政策卡与地域/状态门禁。
- `references/park-policy.md`：用户提供园区正式政策时的使用边界；未提供前不得虚构园区奖励。
- `references/report-template.md`：八部分报告内容与表格。
- `references/html-delivery.md`：HTML/PDF 与 Word 的同源交付、排版和质检。
- `references/word-delivery.md`：仅在用户要求可编辑 Word 时读取的 Word 原生结构与页面复核规则。
- `scripts/run_report_pipeline.py`：`validate → SVG → HTML` 主入口；`--pdf` 和 `--word` 为预置的可选转换。
- `scripts/preflight.py`：跨 Agent 部署预检；检查目录、UTF-8、示例数据和政策门禁，`--smoke` 同时生成示例 HTML。
- `scripts/run_utf8.ps1`：Windows PowerShell 的 UTF-8 启动器，避免 UTF-8 Python 输出被本地代码页错误显示。
- `scripts/validate_report_data.py`、`scripts/validate_text_quality.py`：唯一事实源和文字质量校验。
- `scripts/render_equity_chart.py`、`scripts/render_report_html.py`、`scripts/render_report_pdf.mjs`：图表与渲染器。

示例：

```powershell
# 默认：只生成 HTML
& $py scripts/run_report_pipeline.py examples/flyco-report-data.json --out-dir outputs/flyco

# 按需：HTML + PDF
& $py scripts/run_report_pipeline.py examples/flyco-report-data.json --out-dir outputs/flyco --pdf --node $node

# 按需：HTML + 可编辑 Word
& $py scripts/run_report_pipeline.py examples/flyco-report-data.json --out-dir outputs/flyco --word --node $node
```

所有路径以 Skill 根目录相对定位；不得在 Skill、脚本或示例中写死本机用户目录、磁盘盘符或浏览器绝对路径。运行环境需要时通过 `REPORT_NODE_MODULES`、`REPORT_CHROME_EXECUTABLE` 等环境变量提供。
