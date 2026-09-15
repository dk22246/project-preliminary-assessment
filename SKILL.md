---
name: project-preliminary-assessment
description: Use when 招商人员只提供企业名称或基础资料，需要完成三亚中央商务区企业尽调、股权与财务核验、海南岛内实时政策机会发现和整体落地研判，并交付 HTML、可选 PDF 或 Word 报告。
---

# 项目前期评估

本 Skill 用于三亚中央商务区招商前期判断。先确认企业事实和可迁移经营活动，再实时检索海南岛内政策；不得由政策反向虚构业务。“整体迁入”只是评估情景，不得写成既成事实。

## 公开入口与交付

- 对外唯一命令入口是 `scripts/ppa.py`；其他脚本只属于内部实现，不得形成第二套运行路径。
- 首次部署或 Skill 版本变化时运行一次 `ppa.py setup`。日常项目不得重复下载依赖或运行完整发布测试。
- 每个项目由 `ppa.py start` 创建五份同轮台账和 `workflow-state.json`，不得复制示例企业底稿。
- 两份精简输入完成后运行 `ppa.py compile`，再由 `ppa.py finalize` 对机器生成的五份台账执行唯一一次完整门禁。到达 `report_ready` 后绑定五份台账SHA-256，台账变化必须重新通过该门禁。`advance`仅保留为兼容别名。
- 默认只生成由 `report-data.json` 驱动的HTML。用户明确要求时，才由同一数据附加PDF或可编辑Word；不得分别撰写三套内容。

## 固定工作流

1. 环境就绪；
2. 确认准确企业主体；
3. 按上市或非上市路由完成企业研究；
4. 核验股权与最近三个完整年度财务；
5. 判断鼓励类产业目录；
6. 筛选三亚落地业务并写明承接路径；
7. 按业务和主管部门实时检索政策；
8. 完成报告数据及全部证据门禁；
9. 生成HTML并完成浏览器版式验收，按需附加PDF或Word。

任何阶段都不能跳过。正式交付只接受同一工作区的五份台账、当前Skill指纹和报告就绪哈希。

## 主体确认与企业研究分路

用户只给企业名称时，先判断是集团、上市公司、品牌还是具体经营主体。能够唯一识别时直接继续；存在同名、集团与上市主体混淆、品牌与公司主体混淆时，列出2—4个明确选项确认，确认前不得混用信息。

主体确认后，在 `enterprise-findings.json.enterprise_profile` 只选择一条企业研究路由：

- `listed / listed_disclosure`：以最新年度报告为集中主资料，一次提取主体、业务、产品、近三年财务、国内外收入、股权、政府补助和重大风险；以前年度报告只补历史缺口，企业官网和政府监管只补当前业务、最近一年变化和未解决风险。法定披露已经明确的事实不再用媒体或商业平台重复证明。
- `nonlisted / nonlisted_public_evidence`：跳过无依据的交易所和年报检索。第一层读取企业官网、官方公众号或正式材料中的产品、服务、解决方案和项目；第二层只用政府项目/备案/许可、政府采购/招投标及客户或合作方正式公告验证经营事实；另行核验公开登记、股权和四类官方风险。完成固定路径和一次定向缺口补查后停止，不得无限泛搜。

两条路由改变来源、动作和停止条件，不改变报告结构、鼓励类产业目录判断、三亚落地分析或实时政策检索。上市母公司材料只能补充非上市分析主体的关系背景，不得把集团合并数据改写为该主体自身数据。详细来源和停止门禁见 `references/evidence-intake.md`、`references/business-discovery.md`。

主体和路由写入 `enterprise-findings.json` 后，运行 `ppa.py research-plan` 生成本轮最小行动清单。只读取 `references/research-route-index.md` 中与当前路由对应的一段；不得同时加载上市和非上市执行细则。进入产业目录、政策、Word/PDF或园区政策阶段时，才读取对应参考文件。

两类主体都研究企业关系、主要业务与产品、代表性上下游、国内外业务、近三年经营数据、政府补助和重大风险。上市主体可以依据法定披露核验具体品类排名、市场份额和竞争位置。非上市主体的地位只核验Fortune Global 500、中国企业500强、中国民营企业500强及一项直接相关的行业500强，不扩展普通榜单或泛化荣誉；缺少可靠数据时明确写“本轮公开检索未发现可靠数据，需企业补充”，不得估算或虚构。

## 股权和财务边界

- 企查查和天眼查对两类路由都不是强制入口。只有用户提供可验证导出材料，或当前Agent确有合法可访问页面时，才能作为补充；不得绕过登录、验证码、付费墙或访问控制。
- 所有已画股权节点和连接线必须进入 `equity-evidence.json` 并绑定来源、断言类型和数据时点。完整资料的直接股东比例闭合到100%；部分资料只画已核实关系，不补造剩余股东或比例。公开资料无法支持任何关系时省略图形，说明公开信息边界，但不阻断报告。
- 商业平台与法定披露存在差异时，图中只采用已确认口径，图下用文字说明差异、原因、采用口径、招商影响和核实动作。只有法律主体或核心控制关系冲突会使整份分析失真时才阻断。
- 非上市公司的项目、融资、注册资本、产值、估值和行业均值不得推算收入、利润或纳税；无法取得时保留最近三个年度并标注未公开或需企业补充。

## 产业目录与落地业务

为每项核心现有业务建立唯一 `B` 编号，再按主体性质使用 `references/catalogs/hainan-ftz-encouraged-industry-complete-library.xlsx` 及同源 `complete-industry-catalog-library.json`：内资企业检索《产业结构调整指导目录》鼓励类和海南新增目录；外商投资企业检索全国及海南地区鼓励外商投资目录；两类主体都排查《产业结构调整指导目录》限制类、淘汰类冲突。

输出只允许“明确符合”“存在相近可能”“暂未发现明确匹配”。没有明确匹配项可以正常交付，但仍要列出有实质重合的相近条目和缺失条件。目录文件、版本、主体分流或业务覆盖不完整时才阻断。维护者发布门禁继续执行 `scripts/validate_industry_catalog_library.py`。

三亚落地业务只能来自企业已有业务、组织能力和境内外布局。每项写清三亚主体、人员、合同、收入、利润、结算或投资路径及实际贡献。重资产制造、矿业和农业企业优先判断总部、贸易、投资、结算、品牌、渠道及供应链管理；生产迁入必须有产线、用地、物流、环保、能耗和人员依据。

## 政策检索硬规则

- 先将企业事实展开为可合理相邻的贸易、结算、投资、人员、管理或行业活动，再路由主管部门。不得因为企业尚未明确三亚意向而省略明显相关机会，也不得把固定政策清单机械套用企业。
- 海外业务信号必须逐项处置外贸、EF账户、跨境人民币与外汇结算、ODI、境外直接投资所得税收、跨境资金池和离岸贸易等相邻主题；这是信号级防遗漏，不代表企业必然适用。
- 每个部门按角色完成必需检索路径：所有部门核验主题、部门文件、规范性文件和失效目录；政策主管、申报或执行部门另查申报办理；资金主管部门再查奖补公示。文件关联追溯是发现候选后的方法，不再作为所有部门的机械必查项。
- 每次报告都实时核验正式原文、有效状态、申报或办理状态。`report-data.json.meta.policy_researched_at` 与 `policy-search-ledger.json.researched_at` 必须一致并标记 `realtime`；超过24小时未交付时重新核验。
- 可享受政策只限海南全省、三亚市或三亚中央商务区的正式现行文件；国家政策仅作背景。外省、海南省内非三亚区域专属、征求意见稿、过期文件和新闻解读不得写成可享受权益。
- 正式政策必须说明企业开展什么业务或达到什么条件后，可以获得什么税收优惠、资金支持、办理便利或账户功能。同一优惠的原文、细则和办理口径合并为一项，不重复列示。
- 正式报告政策表只有“匹配政策或工具、匹配原因”两列；完整条件、办理方式、状态、失效及排除原因保留后台。检索失败、附件缺失或资格未知不能写成“没有政策”。

政策机会雷达、主管部门路由、角色化检索回执和结论状态见 `references/policy-opportunity-radar.md`、`references/policy-search-coverage.md`；海南省级、驻琼执行机构和三亚市级来源、正式性及地域门禁见 `references/policy-scope.md`。园区政策仅在用户提供正式材料后按 `references/park-policy.md` 使用。

## 固定报告结构

严格使用 `references/report-template.md` 的七部分：

1. 企业基本情况；
2. 近三年经营数据；
3. 风险与合规情况；
4. 三亚落地业务及落地方式；
5. 企业政策匹配；
6. 综合评估；
7. 参考资料。

企业基本情况使用简明主体表和短段落介绍企业是谁、做什么、经营表现、员工规模和有证据支持的行业地位。业务表只写企业事实，不提前混入三亚推演。产业链只写定位、同类企业、上游、下游和行业共性需求；没有交易证据时不得把代表企业称为已确认供应商、客户或合作伙伴。风险较少时使用简明文字，不制造空表。

HTML、PDF和Word必须读取同一 `report-data.json`。股权图、表格、来源编号和政策内容必须同源；HTML必须通过整页、表格和SVG边界检查。具体结构、样式和可选Word边界见 `references/report-template.md`、`references/html-delivery.md`、`references/word-delivery.md`。

## 命令

```powershell
# 一次性部署；创建项目；生成路由计划；编译后执行一次最终门禁；默认HTML交付
& $py -X utf8 scripts/ppa.py setup
& $py -X utf8 scripts/ppa.py start "企业法律全称" --work-dir work/company
& $py -X utf8 scripts/ppa.py research-plan --work-dir work/company
& $py -X utf8 scripts/ppa.py compile --work-dir work/company
& $py -X utf8 scripts/ppa.py finalize --work-dir work/company
& $py -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company

# 按需取证、检索和导出
& $py -X utf8 scripts/ppa.py collect-web "企业" "主题" --url "https://official.example/..." --out-dir work/company/evidence/topic
& $py -X utf8 scripts/ppa.py collect-equity "企业法律全称" --provider qcc-web --input-json capture.json --out-dir work/company/evidence/qcc
& $py -X utf8 scripts/ppa.py search-catalog "业务关键词" --subject-type domestic
& $py -X utf8 scripts/ppa.py discover-policies --work-dir work/company
& $py -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company --pdf
& $py -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company --word
```

所有路径相对Skill根目录；不得写死本机用户名、磁盘盘符或浏览器路径。完整目录必须按固定Git commit部署，所有文本与结构化数据使用UTF-8。
