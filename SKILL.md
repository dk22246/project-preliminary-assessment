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
- 所有文本和结构化数据均为 UTF-8；读入 JSON 时兼容 UTF-8 BOM，写入时明确指定 UTF-8。跨 Agent 不依赖 PowerShell 编码或参数转发；Python 子进程统一使用 `-X utf8`。
- 新 Agent 首次使用前，必须在 Skill 根目录只运行一条部署门禁命令：`python -X utf8 scripts/verify_skill.py --smoke`。该命令会由 Python 自身执行预检、完整测试、HTML 冒烟和浏览器全页版式验收；不得在 PowerShell 中手工转发 `-m unittest` 参数。若 `python` 不在 PATH，直接用该 Agent 已知的 Python 可执行文件替换 `python`。任一失败时不得生成正式报告。
- 必须先形成 `report-data.json` 和 `equity-evidence.json`，再以 `--equity-evidence <股权台账> --node <Node路径>` 运行 `scripts/run_report_pipeline.py`；不得绕过结构化数据、股权证据校验、浏览器版式门禁或 HTML 渲染器直接手写报告。
- 以固定 Git commit 部署并记录 commit SHA；升级时重新执行上述部署门禁。PDF 和 Word 继续仅按用户要求生成。

## 核心运行顺序

1. **确认主体。** 用户只给企业名称时，先判断名称是集团、上市公司、品牌还是经营主体。唯一可识别时直接研究；存在同名、集团与上市主体混淆、品牌与主体混淆时，列出 2—4 个明确选项，请用户确认。运行环境有企查查 MCP 时，可用 `get_company_by_query` 返回候选并以法律全称、统一社会信用代码锚定；确认前不得混用信息。
2. **研究企业并核验股权。** 建立企业主体、股权结构、主要业务与产品、行业竞争位置、代表性上下游、国内外业务、近三年经营数据、政府补助和重大风险的事实卡。股权查询优先使用企查查 MCP/CLI 获取工商股东并逐层穿透，天眼查 API 复核当前股东、受益人和历史股东；上市公司以法定披露定案。全部结果统一写入 `equity-evidence.json`，每个股权节点和连接线绑定来源与数据时点；平台不可用时保留失败回执并用法定来源降级，不得补猜。规则见 `references/entity-resolution.md`、`references/equity-evidence.md`。年报不是能力发现的唯一来源；将官网发展历程、新闻、产品服务、品牌/IP、赛事活动、平台生态、供应链、投资和管理职能写入 `research-ledger.json` 的事实台账与业务候选池。每个候选必须纳入、合并或排除，确认候选完整后再压缩为正式业务。需要提高网页取证效率时，可先生成 `evidence.json`；采集结果只是事实证据，不是政策资格。
3. **强制判断鼓励类产业目录。** 为 `businesses` 每项核心现有业务分配唯一 `B` 类编号，使用随 Skill 打包的海南新增目录界定指引和现行国家目录逐项判断。输出只能为“明确符合”“存在相近可能”“暂未发现明确匹配”；没有明确匹配项正常交付，AI仍须主动判断并列出有实质重合的相近条目及缺失条件。只有目录版本、来源、检索或业务覆盖未完成时才阻断。规则见 `references/encouraged-industry-assessment.md`。
4. **拆解招商价值。** 从已处置候选中识别可在三亚中央商务区实质运营的业务与管理职能；不得由政策反向虚构业务。
5. **设计落地路径并路由主管部门。** 对每项业务写清三亚承接主体、职能、人员、合同、收入、利润、结算或投资路径，以及可形成的税收、贸易、投资、就业、品牌和产业带动。将经营动作拆成政府管理事项，按 `references/department-routing.json` 或经职责依据核验的动态路由，逐项对应主管部门。
6. **检索、核验并提炼重点政策。** 先按事实层、上位事项层、相邻事项层展开业务语义，再为每个主管部门建立角色和七路径检索回执。主题检索、目录扫描、申报/兑现、失效目录、文件关联和附件取证任一失败或未完成，必须写为 `research_incomplete` 并停止交付；不得写成“无政策”。发现现行政策而企业资格未明时，必须写为 `conditional_opportunity`。只有现行、已纳入且通过正式性、地域、条件、办理方式和企业承接路径核验的候选政策，才能成为重点政策。规则见 `references/policy-scope.md`、`references/policy-discovery.md`、`references/policy-search-coverage.md`。
7. **汇总成唯一事实源。** 将报告结论写入符合 `schemas/report.schema.json` 的 `report-data.json`，股权证据写入符合 `schemas/equity-evidence.schema.json` 的 `equity-evidence.json`，业务链路写入 `research-ledger.json`，动态检索回执写入 `policy-search-ledger.json`。主流水线必须传入 `--equity-evidence`、`--research-ledger` 和 `--policy-search-ledger`；如使用网页采集，同时传入已校验的 `--evidence`。数据、鼓励类目录、股权、文本、研究底稿、动态检索覆盖和政策范围校验全部通过后才渲染输出。
8. **生成并复核交付物。** 运行 `scripts/run_report_pipeline.py --equity-evidence <股权台账> --node <Node路径>` 默认生成 HTML；仅在用户要求时附加 `--pdf` 或 `--word`。所有表格行数、列宽和表头必须先通过结构校验；财务数据必须声明成对的 `meta.financial_currency` 与 `meta.financial_unit`，营业收入、净利润单元格只写数值，同比单元格只能写百分比或短状态，说明移至 `change_note` 表下注释。HTML 经 `scripts/verify_html_layout.mjs` 检查整页横向越界、全部报告表格、SVG 图表元素与 SVG 文本重叠；任一失败都禁止生成或交付 HTML、PDF、Word。PDF 和 Word 均须复核文件结构、文字、目录、图表、表格和来源。

## 企业与落地业务判断

- 研究主体关系：集团、上市公司、品牌、子品牌、子公司、控股股东与最终控制方。股权关系仅按 `equity-evidence.json` 已核验的上下级关系绘制，每个节点和连接线必须有 `E` 类来源编号；平台计算的实际控制关系必须标明“推定/疑似/平台穿透”，不用文字框堆叠。
- 股权图只画已确认的共同事实。企查查、天眼查与法定披露存在比例、时点或局部关系差异时，不得把冲突内容并排画进图中；必须在图下生成“股权数据差异说明”，写清各方口径、可能原因、采用口径、招商影响和核实动作。一般差异继续交付；重要局部差异隐藏争议节点或连线后继续交付；只有未解决的法律主体或核心控制关系冲突足以使整份企业分析失真时，才阻断报告。具体字段和门禁见 `references/equity-evidence.md`。
- 业务拆分必须覆盖主要业务板块、主要产品、主要承载主体、客户/收入来源、国内外业务布局和三亚潜在结合点。相关方法见 `references/business-decomposition.md`。
- 重资产制造、矿业、农业企业不得机械假设产线迁入。优先判断总部、贸易、投资、结算、品牌、渠道与供应链管理；生产迁入须有产线、用地、物流、环保、能耗和人员事实依据。
- “最适合落地”不是泛泛描述。每项必须说明企业事实基础、可分离性、中央商务区实质运营条件及实际贡献路径。

## 政策硬规则

- 可享受政策仅限海南全省、三亚市或三亚中央商务区的正式、现行文件；国家政策仅作制度背景。外省、海南省内非三亚区域专属、征求意见稿、过期文件和新闻解读不得写成可享受权益。
- 不设企业所得税、个人所得税、EF 账户、ODI、总部认定等固定覆盖清单。仅当企业的拟落地业务触发相应主题时检索；例如迁入总部与人员才检索总部、企业所得税与人才个税，跨境贸易才检索 EF 账户、跨境人民币和外贸，境外投资才检索 ODI 与境外所得政策。
- 不得因业务事实不足而静默省略政策主题。每项拟落地业务的检索结果必须归入“可适用（条件待核）”“条件型政策机会”“暂未触发”“现有条件不适用”“未发现现行政策”或“检索未完成（禁止交付）”之一；后四类必须写明原因和下一步需向企业核实的事实。`no_current_policy` 仅在所有相关部门七路径完成且未发现现行候选政策时可用。该结论留在后台台账和招商工作底稿，不默认作为报告中的“待核政策事项”展示。
- 每条政策先用一句话说明“企业开展什么业务或达到什么条件后，可以获得什么税收优惠、资金支持、办理便利或账户功能”，再写匹配逻辑、条件、办理方式和实际价值。
- 正式报告默认采用整体落地情景：企业在三亚设立并实质运营主体，承接报告已确定的总部管理、品牌、贸易、结算、投资或行业功能。报告聚焦对招商谈判有直接价值的重点政策，不把“条件型政策机会”作为表格中的结论标签；改为在“享受前提及三亚承接”列写清条件。
- 同一项优惠的基础政策、实施细则、认定公告或申报口径不得拆成重复行；合并为一行并在政策依据中并列官方原文。政策名称须先说清企业能得到什么：例如“高端紧缺人才个人所得税优惠（实际税负15%封顶）”“EF账户（多功能自由贸易账户）”，不得只堆砌文件标题。
- 拟写入报告的政策卡必须通过 `scripts/validate_policy_scope.py`；全部业务检索结论必须先通过 `scripts/validate_policy_search_coverage.py`，再通过 `scripts/validate_business_policy_ledger.py`。前者是政策正式性、地域、状态与企业承接路径门槛；动态检索校验防止把缺检索、网页失败或附件失败误写为无政策；业务台账校验防止业务或政策主题遗漏。三者均不代表企业已取得资格。

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
- `references/equity-evidence.md`：企查查 MCP/CLI、天眼查 API、法定披露的股权接入顺序、归一化和冲突处理。
- `references/evidence-intake.md`：企业、财务、风险公开信息来源和禁用来源。
- `references/source-registry.md`：网页取证的允许来源、企业官网显式登记与禁止范围。
- `references/business-decomposition.md`：业务拆分和落地业务筛选。
- `references/encouraged-industry-assessment.md`、`references/catalogs/*`：鼓励类产业目录逐业务三档判断、内置数据和正式来源版本。
- `references/business-discovery.md`、`references/department-routing.json`、`references/policy-discovery.md`、`references/policy-search-coverage.md`：业务能力候选、通用主管部门路由、候选政策发现和动态检索覆盖；不得只靠文字提示跳过。
- `references/policy-scope.md`：官方政策来源、搜索顺序、政策卡与地域/状态门禁。
- `references/park-policy.md`：用户提供园区正式政策时的使用边界；未提供前不得虚构园区奖励。
- `references/report-template.md`：八部分报告内容与表格。
- `references/html-delivery.md`：HTML/PDF 与 Word 的同源交付、排版和质检。
- `references/word-delivery.md`：仅在用户要求可编辑 Word 时读取的 Word 原生结构与页面复核规则。
- `scripts/run_report_pipeline.py`：`数据及股权证据 validate → SVG → HTML → 浏览器全页版式门禁` 主入口，必须提供 `--equity-evidence` 和 `--node`；`--pdf` 和 `--word` 为预置的可选转换。
- `scripts/collect_equity_provider.py`、`scripts/validate_equity_evidence.py`：商业平台原始股权数据采集与逐节点、逐连线证据门禁；密钥只由运行环境提供。
- `scripts/collect_web_evidence.py`、`scripts/validate_evidence.py`：可选的公开网页证据采集与台账门禁；只增强取证，不改变政策卡校验。
- `scripts/validate_research_ledger.py`：强制校验企业事实—业务候选—主管部门—候选政策—正式政策卡的完整追溯链。
- `scripts/validate_policy_search_coverage.py`：强制校验业务语义、部门角色、七条检索路径、附件状态和报告结论边界；任一 `research_incomplete` 都阻断交付。
- `scripts/verify_skill.py`：跨 Agent 唯一部署门禁；以当前 Python 解释器依次运行预检、完整测试和可选 HTML 冒烟，不依赖 PowerShell。
- `scripts/preflight.py`：由部署门禁调用的目录、UTF-8、示例数据和政策预检；`--smoke` 同时生成示例 HTML 并进行浏览器全页版式验收。
- `scripts/run_utf8.ps1`：仅供本机 PowerShell 需要改善终端显示时可选使用，不是跨 Agent 门禁。
- `scripts/validate_report_data.py`、`scripts/validate_text_quality.py`：唯一事实源和文字质量校验。
- `scripts/render_equity_chart.py`、`scripts/render_report_html.py`、`scripts/render_report_pdf.mjs`、`scripts/verify_html_layout.mjs`：图表、渲染器与浏览器版式验收。

示例：

```powershell
# 默认：只生成 HTML，但必须通过浏览器版式验收
& $py scripts/run_report_pipeline.py examples/flyco-report-data.json --equity-evidence examples/flyco-equity-evidence.json --research-ledger examples/flyco-research-ledger.json --policy-search-ledger examples/flyco-policy-search-ledger.json --out-dir outputs/flyco --node $node

# 如本次使用网页取证，先校验证据台账并接入主流水线
& $py scripts/validate_evidence.py evidence/enterprise/evidence.json
& $py scripts/run_report_pipeline.py examples/flyco-report-data.json --equity-evidence equity-evidence.json --research-ledger research-ledger.json --policy-search-ledger policy-search-ledger.json --evidence evidence/enterprise/evidence.json --out-dir outputs/flyco --node $node

# 按需：HTML + PDF
& $py scripts/run_report_pipeline.py examples/flyco-report-data.json --equity-evidence examples/flyco-equity-evidence.json --research-ledger examples/flyco-research-ledger.json --policy-search-ledger examples/flyco-policy-search-ledger.json --out-dir outputs/flyco --pdf --node $node

# 按需：HTML + 可编辑 Word
& $py scripts/run_report_pipeline.py examples/flyco-report-data.json --equity-evidence examples/flyco-equity-evidence.json --research-ledger examples/flyco-research-ledger.json --policy-search-ledger examples/flyco-policy-search-ledger.json --out-dir outputs/flyco --word --node $node
```

所有路径以 Skill 根目录相对定位；不得在 Skill、脚本或示例中写死本机用户目录、磁盘盘符或浏览器绝对路径。运行环境需要时通过 `REPORT_NODE_MODULES`、`REPORT_CHROME_EXECUTABLE` 等环境变量提供。
