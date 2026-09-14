---
name: project-preliminary-assessment
description: Use when 招商人员只提供企业名称或基础资料，需要完成三亚中央商务区企业尽调、股权与财务核验、海南岛内实时政策机会发现和整体落地研判，并交付 HTML、可选 PDF 或 Word 报告。
---

# 项目前期评估

本 Skill 面向三亚中央商务区招商前期决策。它不是固定政策清单工具：先确认企业事实，再把已存在的业务、组织能力和境内外布局展开为可在三亚承接的相邻经营活动，由这些事实信号触发海南岛内实时政策和办理工具检索。所有结论均区分公开事实、政策条件与招商推演；“整体迁入”仅是推演情景，不得写成既成事实。

## 默认交付

默认只生成 `report-data.json` 驱动的 HTML 报告，HTML 是主阅读版。用户明确需要时，才从这份最终 HTML 转换 PDF，或从同一份数据生成可编辑 Word。不得分别撰写三套内容，也不得以聊天正文代替文件。

## 跨 Agent 部署门禁

- 仅通过 Git 仓库完整克隆或复制整个 Skill 目录，不得只复制 `SKILL.md`、聊天文本或单个脚本。
- 所有文本和结构化数据均为 UTF-8；读入 JSON 时兼容 UTF-8 BOM，写入时明确指定 UTF-8。跨 Agent 不依赖 PowerShell 编码或参数转发；Python 子进程统一使用 `-X utf8`。
- 对外唯一命令入口是 `scripts/ppa.py`。新设备或版本升级只执行一次 `ppa.py setup`：它优先复用已验证兼容运行时，缺少时才安装项目依赖和 Chromium，按需安装 Word 组件并完成部署验证；日常任务不会重复下载或运行完整测试。Git commit 或关键文件指纹变化时必须重新部署。不得把 Windows 商店占位符当作运行时。
- 每个正式项目只能由 `ppa.py start` 创建：它生成同轮五份台账和 `workflow-state.json`。不得复制飞科示例作为新企业底稿；飞科文件只用于显式 fixture 模式下的发布测试。
- 工作流状态必须按顺序推进：环境就绪、主体确认、企业研究、股权与财务、产业目录、落地业务、实时政策研究、报告就绪、HTML验收、可选导出。任何跳过、台账不同目录或报告就绪后台账变更，都会阻断正式交付。
- 以固定 Git commit 部署并记录 commit SHA；升级时重新执行上述部署门禁。PDF 和 Word 继续仅按用户要求生成。

## 核心运行顺序

1. **确认主体。** 用户只给企业名称时，先判断名称是集团、上市公司、品牌还是经营主体。唯一可识别时直接研究；存在同名、集团与上市主体混淆、品牌与主体混淆时，列出 2—4 个明确选项，请用户确认。Agent 可使用已有合法浏览器登录态访问企查查网页或天眼查网页，以页面显示的法律全称和统一社会信用代码锚定主体；确认前不得混用信息，不得绕过登录、验证码、付费墙或访问控制。
2. **锁定披露类型后研究企业并核验股权。** 主体确认后，必须在 `research-ledger.json.enterprise_profile` 将本报告分析主体标记为 `listed / listed_disclosure` 或 `nonlisted / nonlisted_public_evidence`，并绑定判断来源。该路由只改变企业证据来源、搜索顺序和停止条件，不改变研究内容、报告结构或后续实时政策检索。上市主体优先一次性使用交易所及法定披露完成近三年财务、业务、股权与风险核验；非上市主体直接跳过无依据的交易所和年报检索，优先企业官方材料、政府监管、工商股权、项目经营与风险记录。上市母公司材料可补充非上市分析主体，但不得替代该主体自己的数据。完整路由和停止条件见 `references/evidence-intake.md`、`references/business-discovery.md`。

   两类主体均建立企业主体、股权结构、主要业务与产品、行业竞争位置、代表性上下游、国内外业务、近三年经营数据、政府补助和重大风险的事实卡。行业位置必须写明具体品类、证据状态、统计时点和来源；有排名、份额或第一梯队证据时明确写出，没有可靠证据时写“本轮未发现可核验公开排名或市场份额”，不得改写为“头部企业”或臆测 Top1。企查查网页和天眼查网页用于实时核验工商股东、持股比例、实际控制人或受益人页面标记、历史变化和主要子公司；上市公司始终以交易所、年报等法定披露定案。网页可见结果先写入符合 `schemas/equity-web-capture.schema.json` 的标准化取证 JSON，必须逐项记录五类覆盖处置；再由 `scripts/collect_equity_provider.py` 生成可校验取证链并形成 `equity-evidence.json`。每个股权节点和连接线绑定来源、断言类型与数据时点；直接股东比例必须闭合到100%，不能拆到具体股东时以“其他股东合计”补足并绑定同一法定披露来源，禁止重复计算。网页失败详情留在后台台账；报告只显示最终采用来源、编号和数据时点，只有实质冲突才显示差异说明。规则见 `references/entity-resolution.md`、`references/equity-evidence.md`。
3. **强制判断鼓励类产业目录。** 为 `businesses` 每项核心现有业务分配唯一 `B` 类编号，先判断企业主体性质，再使用 `references/catalogs/hainan-ftz-encouraged-industry-complete-library.xlsx` 和同源的 `complete-industry-catalog-library.json` 分流检索：内资企业覆盖《产业结构调整指导目录》鼓励类与海南新增目录；外商投资企业覆盖全国鼓励外商投资目录与海南地区目录；两类主体均须以《产业结构调整指导目录》限制类、淘汰类执行冲突排查。输出只能为“明确符合”“存在相近可能”“暂未发现明确匹配”；没有明确匹配项正常交付，AI仍须主动判断并列出有实质重合的相近条目及缺失条件。只有目录文件、来源版本、主体分流、检索或业务覆盖未完成时才阻断。发布和部署预检必须运行 `scripts/validate_industry_catalog_library.py`。规则见 `references/encouraged-industry-assessment.md`。
4. **拆解招商价值。** 从已处置候选中识别可在三亚中央商务区实质运营的业务、管理职能和相邻经营活动；不得由政策反向虚构业务。
5. **建立政策机会雷达。** 将每条企业事实信号展开为可能在三亚承接的贸易、结算、投资、人员、管理或行业活动，逐项记录 `surfaced / merged / excluded / expired / not_current / pending_evidence / research_incomplete` 处置。海外产品、渠道或境外投资信号必须动态研判外贸、EF账户、跨境结算、ODI、境外直接投资所得税收、跨境资金池和离岸贸易等相邻主题；这是防遗漏路由，不是固定可享受政策清单。规则见 `references/policy-opportunity-radar.md`。
6. **设计落地路径并路由主管部门。** 对可承接活动写清三亚主体、职能、人员、合同、收入、利润、结算或投资路径，以及可形成的税收、贸易、投资、就业、品牌和产业带动。将经营动作拆成政府管理事项，按 `references/department-routing.json` 或经职责依据核验的动态路由，逐项对应主管部门。
7. **实时检索、核验并提炼重点政策。** 每次报告重新核验官方原文、现行状态和申报状态，`report-data.json.meta.policy_researched_at` 必须与 `policy-search-ledger.json.researched_at` 一致且标记 `realtime`；正式报告超过24小时未完成交付时重新检索。为每个机会主题和主管部门建立角色及七路径回执。任一路径或附件未完成，写为 `research_incomplete` 并停止交付；过期或非现行文件只留后台处置。只有现行、已纳入且通过正式性、地域、条件、办理方式和企业承接路径核验的正向机会，才能进入报告。
8. **汇总成唯一事实源。** 将报告结论和 `policy_opportunity_radar` 写入符合 `schemas/report.schema.json` 的 `report-data.json`，股权证据写入 `equity-evidence.json`，业务链路写入 `research-ledger.json`，实时检索回执写入 `policy-search-ledger.json`。全部门禁通过后才渲染。

   企业基本情况必须按 `references/ranking-registry.json` 完成 Fortune Global 500、中国企业500强和中国民营企业500强的当前最新正式年度核验；状态只能为 `listed`、`group_listed`、`not_listed` 或 `research_incomplete`，并逐项绑定对应最新官方 E 类来源。注册表缺失、损坏或未核验时阻断，不得回退到硬编码旧年度。产业链仅按定位、同类企业、上游、下游、行业共性需求五段记录；行业共性需求仅为 `industry_inference`，不得作为企业事实或政策触发依据。无 `transaction_evidence=true` 时，不得将代表企业称为已确认供应商、客户或合作伙伴；不得加入产业集群启示或招商对象标签。
9. **生成并复核交付物。** 通过 `ppa.py deliver` 默认生成 HTML；仅在用户要求时加 `--pdf` 或 `--word`。控制器先验证当前环境、五份同目录台账、报告就绪哈希和全部数据门禁，HTML再通过整页、表格和SVG版式验收；任一失败都禁止交付。

## 企业与落地业务判断

- 研究主体关系：集团、上市公司、品牌、子品牌、子公司、控股股东与最终控制方。股权关系仅按 `equity-evidence.json` 已核验的上下级关系绘制，每个节点和连接线必须有 `E` 类来源编号；平台计算的实际控制关系必须标明“推定/疑似/平台穿透”，不用文字框堆叠。
- 股权图只画已确认的共同事实。企查查、天眼查与法定披露存在比例、时点或局部关系差异时，不得把冲突内容并排画进图中；必须在图下生成“股权数据差异说明”，写清各方口径、可能原因、采用口径、招商影响和核实动作。一般差异继续交付；重要局部差异隐藏争议节点或连线后继续交付；只有未解决的法律主体或核心控制关系冲突足以使整份企业分析失真时，才阻断报告。具体字段和门禁见 `references/equity-evidence.md`。
- 业务拆分只覆盖企业已经存在的主要业务板块、主要产品、主要承载主体、客户/收入来源和国内外业务布局。三亚承接判断统一放在后续“落地业务及落地方式”中，不得在企业业务事实表中提前混入推演。相关方法见 `references/business-decomposition.md`。
- 重资产制造、矿业、农业企业不得机械假设产线迁入。优先判断总部、贸易、投资、结算、品牌、渠道与供应链管理；生产迁入须有产线、用地、物流、环保、能耗和人员事实依据。
- “最适合落地”不是泛泛描述。每项必须说明企业事实基础、可分离性、中央商务区实质运营条件及实际贡献路径。

## 政策硬规则

- 可享受政策仅限海南全省、三亚市或三亚中央商务区的正式、现行文件；国家政策仅作制度背景。外省、海南省内非三亚区域专属、征求意见稿、过期文件和新闻解读不得写成可享受权益。
- 不设企业所得税、个人所得税、EF账户、ODI、总部认定等固定覆盖清单。政策检索由企业事实信号及其合理相邻经营活动触发，不要求企业事先明确三亚意图，也不得因海南有政策而虚构企业业务。
- 不得因企业尚未表达三亚意向而静默省略政策主题。每条企业事实信号及其合理相邻经营活动都必须形成机会处置；进入具体检索的主题必须归入“可适用（条件待核）”“条件型政策机会”“暂未触发”“现有条件不适用”“未发现现行政策”或“检索未完成（禁止交付）”之一。非正向结论必须写明原因和下一步需核实的事实。`no_current_policy` 仅在所有相关部门七路径完成且未发现现行候选政策时可用，并只留后台台账。
- 每条政策先用一句话说明“企业开展什么业务或达到什么条件后，可以获得什么税收优惠、资金支持、办理便利或账户功能”，再写匹配逻辑、条件、办理方式和实际价值。
- 正式报告的政策表只保留“匹配政策或工具、匹配原因”两列。政策名称直接说明优惠或功能；匹配原因用一句话合并企业事实、三亚承接活动和触发条件。完整条件、办理方式、现行状态、失效政策及排除理由只留后台台账和参考资料，不堆入前台表格。
- 同一项优惠的基础政策、实施细则、认定公告或申报口径不得拆成重复行；合并为一行并在政策依据中并列官方原文。政策名称须先说清企业能得到什么：例如“高端紧缺人才个人所得税优惠（实际税负15%封顶）”“EF账户（多功能自由贸易账户）”，不得只堆砌文件标题。
- 拟写入报告的政策卡必须通过 `scripts/validate_policy_scope.py`；全部业务检索结论必须先通过 `scripts/validate_policy_search_coverage.py`，再通过 `scripts/validate_business_policy_ledger.py`。前者是政策正式性、地域、状态与企业承接路径门槛；动态检索校验防止把缺检索、网页失败或附件失败误写为无政策；业务台账校验防止业务或政策主题遗漏。三者均不代表企业已取得资格。

## 固定报告结构

严格使用 `references/report-template.md` 的七个一级部分：

1. 企业基本情况（主体认定与企业概况、股权架构、业务及产品、鼓励类产业目录、产业链上下游）
2. 近三年经营数据（经营表、政府补助明细与分析）
3. 风险与合规情况
4. 三亚落地业务及落地方式
5. 企业政策匹配
6. 综合评估
7. 参考资料

企业基本情况必须置于正文首节。主体认定采用简明两列表格，表后用短段落说明企业是谁、主要做什么、最近经营表现、员工规模和有证据支持的行业地位。不得另设“项目整体判断”重复概括，也不得另设独立的行业地位小节重复陈述。

上市与非上市企业使用同一报告结构和研究主题。非上市企业完成规定来源检索后仍无法取得可靠财务、员工或行业排名数据时，必须在对应字段写明“本轮公开检索未发现可靠数据，需企业补充”或等义的明确证据边界；该结果属于已完成检索，不得填零、估算、虚构排名，也不得因公开披露不足无限扩展搜索。

报告内的来源均用 `E/F/R/P` 编号回溯。风险事项少时可用简明文字，不得为了形式制造空表。关键事实、数字、政策和风险必须有可定位来源。

## 文件与执行入口

- `references/entity-resolution.md`：主体确认与股权核验。
- `references/equity-evidence.md`：企查查网页、天眼查网页、法定披露的股权取证顺序、归一化和冲突处理。
- `references/evidence-intake.md`：企业、财务、风险公开信息来源和禁用来源。
- `references/source-registry.md`：网页取证的允许来源、企业官网显式登记与禁止范围。
- `references/business-decomposition.md`：业务拆分和落地业务筛选。
- `references/encouraged-industry-assessment.md`、`references/catalogs/hainan-ftz-encouraged-industry-complete-library.xlsx`、`references/catalogs/complete-industry-catalog-library.json`：完整产业目录、主体分流、海南新增界定指引、限制类/淘汰类冲突排查和逐业务三档判断。
- `references/business-discovery.md`、`references/policy-opportunity-radar.md`、`references/department-routing.json`、`references/policy-discovery.md`、`references/policy-search-coverage.md`：企业事实信号、相邻经营活动、主管部门路由、候选政策发现和动态检索覆盖；不得只靠文字提示跳过。
- `references/policy-scope.md`：官方政策来源、搜索顺序、政策卡与地域/状态门禁。
- `references/park-policy.md`：用户提供园区正式政策时的使用边界；未提供前不得虚构园区奖励。
- `references/report-template.md`：七部分报告内容与表格。
- `references/html-delivery.md`：HTML/PDF 与 Word 的同源交付、排版和质检。
- `references/word-delivery.md`：仅在用户要求可编辑 Word 时读取的 Word 原生结构与页面复核规则。
- `scripts/ppa.py`：唯一公开入口，负责一次性部署、工作区创建、阶段状态、受控推进和正式交付。
- `scripts/workflow_state.py`：内部状态机；为每轮正式报告绑定阶段回执、版本指纹和五份台账哈希。
- `scripts/collect_equity_provider.py`、`scripts/validate_equity_evidence.py`：商业平台网页标准化取证、确定性 fragment 输出与逐节点、逐连线证据门禁；浏览器登录态由 Agent 合法持有且不得写入 Skill 或证据文件。
- `scripts/collect_web_evidence.py`、`scripts/validate_evidence.py`：可选的公开网页证据采集与台账门禁；只增强取证，不改变政策卡校验。
- `scripts/validate_research_ledger.py`：强制校验企业事实—业务候选—主管部门—候选政策—正式政策卡的完整追溯链。
- `scripts/validate_policy_search_coverage.py`：强制校验业务语义、部门角色、七条检索路径、附件状态和报告结论边界；任一 `research_incomplete` 都阻断交付。
- `scripts/search_industry_catalog.py`、`scripts/build_industry_catalog_library.py`、`scripts/validate_industry_catalog_library.py`：按内资/外商投资企业分流召回目录候选、从统一工作簿重建结构化检索库，并校验条数、来源、界定指引及限制类/淘汰类冲突路由。
- 运行时、初始化、验证和渲染脚本均为 `ppa.py` 的内部组件，不得作为另一个公开工作流调用。
- `scripts/discover_current_policies.py`、`scripts/policy_cache.py`：按主管部门路由受控并发发现政策，并在每轮访问官方来源后复验缓存；不得用旧缓存冒充实时检索。
- `scripts/validate_research_stop_gate.py`、`scripts/validate_policy_evidence.py`：分别阻断未完成企业必查事项的研究底稿，以及缺少本轮官方原文、哈希、效力和申报状态证据的前台政策。
- `scripts/verify_skill.py`：维护者发布门禁；`--release` 运行预检和完整测试，`--smoke` 额外运行示例HTML，不得在每份报告前调用。
- `scripts/preflight.py`：由部署门禁调用的目录、UTF-8、示例数据和政策预检；`--smoke` 同时生成示例 HTML 并进行浏览器全页版式验收。
- `scripts/validate_report_data.py`、`scripts/validate_text_quality.py`：唯一事实源和文字质量校验。
- `scripts/render_equity_chart.py`、`scripts/render_report_html.py`、`scripts/render_report_pdf.mjs`、`scripts/verify_html_layout.mjs`：图表、渲染器与浏览器版式验收。

示例：

```powershell
# 一次性部署或版本升级
& $py -X utf8 scripts/ppa.py setup

# 新企业工作区、阶段确认和默认 HTML 交付
& $py -X utf8 scripts/ppa.py start "企业法律全称" --work-dir work/company
& $py -X utf8 scripts/ppa.py advance --work-dir work/company
& $py -X utf8 scripts/ppa.py status --work-dir work/company
& $py -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company

# 按需：HTML + PDF 或可编辑 Word
& $py -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company --pdf
& $py -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company --word
```

所有路径以 Skill 根目录相对定位；不得在 Skill、脚本或示例中写死本机用户目录、磁盘盘符或浏览器绝对路径。运行环境需要时通过 `REPORT_NODE_MODULES`、`REPORT_CHROME_EXECUTABLE` 等环境变量提供。
