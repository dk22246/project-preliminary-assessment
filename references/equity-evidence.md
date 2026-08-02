# 股权数据平台接入与证据门禁

## 核心原则

股权图只呈现有证据的节点和连线。先锁定准确法律主体及统一社会信用代码，再查询股东；不得用品牌名、集团简称或证券简称直接拼接不同主体的数据。

法定披露优先：上市公司的控股股东、实际控制人、十大股东和并表子公司，以交易所公告、年度报告和招股说明书定案；企查查、天眼查用于主体锚定、工商股东、历史变化和穿透关系复核。非上市公司的工商登记股东可使用商业平台结构化数据，但关键控制关系仍应尽量与国家企业信用信息公示系统、企业正式材料或监管文件交叉核验。

## 接入顺序

1. **企查查 MCP。** 运行环境已配置 `qcc-company` 时，简称或品牌先调用 `get_company_by_query`；唯一主体确认后调用 `get_shareholder_info`。企业股东继续逐层查询，直到自然人、上市公司公众股东、国资控制主体或证据边界。WorkBuddy 等兼容 MCP 的 Agent 使用同一顺序。
2. **企查查 CLI。** MCP 不可用而已配置官方 CLI 时，运行 `scripts/collect_equity_provider.py <法律主体> --provider qcc-cli --out-dir <目录>`，保留原始 JSON 查询包。CLI 密钥由 `qcc init` 在运行环境配置，不得写入 Skill。
3. **企查查网页取证。** MCP、API或CLI在当前Agent不可调用但网页可访问时，必须继续使用该Agent已有的网页抓取或浏览器能力检索法律主体、股东和历史变更。将可见页面结果保存为统一网页取证JSON，再运行 `scripts/collect_equity_provider.py <法律主体> --provider qcc-web --input-json <取证JSON> --out-dir <目录>`；不得把“接口未配置”写成“企查查不可用”。
4. **天眼查 API 或网页复核。** 设置 `TYC_API_TOKEN` 时调用API；否则在网页可访问时使用同样的标准化网页取证流程并以 `tianyancha-web` 入账。令牌、Cookie和登录信息不得进入Skill或证据文件。
5. **法定来源补证。** 上市公司、国资主体、境外主体、复杂合伙架构或平台结果冲突时，补查交易所、监管机构、企业注册机关和企业法定披露。

官方接入资料：

- 企查查 MCP 与 CLI：<https://agent.qcc.com/guide>
- 企查查股权数据能力：<https://agent.qcc.com/data>
- 天眼查股权结构图接口：<https://open.tianyancha.com/open/453>
- 天眼查股东出资接口：<https://open.tianyancha.com/open/997>
- 天眼查最终受益人接口：<https://open.tianyancha.com/open/945>
- 天眼查历史股东接口：<https://open.tianyancha.com/open/877>

## 统一证据格式

不论数据来自 MCP、CLI、API 还是法定披露，都必须归一化为 `equity-evidence.json`，并符合 `schemas/equity-evidence.schema.json`。至少记录：

- 精确法律主体及统一社会信用代码；
- 每个平台是否成功、查询时间及失败原因；
- 每条来源的提供方、工具或接口、查询词和可定位记录；
- 每个节点的名称、主体类型、断言类型和 `E` 类来源编号；
- 每条连线的关系、持股比例或“比例未披露”、数据时点、断言类型和来源编号；
- 平台之间、平台与法定披露之间的冲突及处理状态。

报告 `equity.nodes` 和 `equity.edges` 的每一项都必须填写 `evidence_source_ids`。先运行：

```powershell
& $py -X utf8 scripts/validate_equity_evidence.py equity-evidence.json --report-data report-data.json
```

主流水线必须传入 `--equity-evidence equity-evidence.json`；未通过时不得绘制股权图。

报告 `equity.evidence_summary` 固定公开本次实际尝试渠道、成功来源、采用口径和状态说明，并与台账逐项一致。只有真实成功回执和返回数据才能写“企查查/天眼查已核验”；仅存在适配代码时只能写“预留接口，当前未取得成功回执”。

## 断言边界

- `registry_fact`：工商登记股东、登记持股比例等结构化事实。
- `legal_disclosure`：年报、交易所公告或监管文件明确披露的控制关系。
- `consolidation_scope`：仅能证明并表或控制，持股比例未披露时不得补猜。
- `provider_calculation`：平台穿透或算法计算结果。不得把平台计算结果直接写成已确认的实际控制人；关系名称必须带“平台穿透推定”“疑似”或同等限定。

股权比例缺失时写“比例未披露”。两家平台结果冲突、数据时点不一致或主体标识无法对齐时，必须写入 `conflicts`，不得静默选择其中一家，也不得用图形排版掩盖证据缺口。

每项差异必须填写唯一 `C` 编号，以及差异字段、严重程度、处理状态、各方口径、可能原因、采用口径、招商影响、后续核实动作、图形处理方式、影响的节点或连线和 `E` 类来源编号。报告 `equity.conflict_disclosures` 必须逐项复制同一结构并通过一致性校验；渲染器只把它作为股权图下方的“股权数据差异说明”文字输出，不画入 SVG。

按以下三级处理：

- `general`：比例尾差、更新时间、统计口径或历史/当前状态差异，但主体和股东关系可以确认。保留已确认部分，争议比例不绘制或写“比例待核”，`review_status` 设为 `qualified_complete`，报告继续生成。
- `material_local`：局部股东、子公司或控制连接存在重要差异，但不影响准确企业主体及整体分析。将 `graph_action` 设为 `omit_disputed_part`，从股权图删除争议节点或连线，文字说明后继续生成。
- `subject_critical`：法律主体、集团与上市主体对应关系或核心控制关系存在未解决冲突，可能导致企业、财务或风险信息混用。将 `review_status` 设为 `blocked`，并阻断整份报告；如法定披露已经定案，将状态改为 `resolved`，采用法定披露并仍说明平台差异。

存在未解决但非根本性的差异时使用 `qualified_complete`；存在未解决的主体或核心控制关系冲突时使用 `blocked`；没有未解决差异时使用 `complete`，平台降级但法定来源已完整补证时使用 `fallback_complete`。图片永远只呈现已经确认的事实，文字负责解释差异、影响和待核动作。

## 降级规则

商业平台未授权、额度不足或接口失败时，必须保留 `unavailable` 或 `error` 回执及原因，再使用法定披露或官方登记材料。只有替代来源能够逐节点、逐连线支撑报告股权图时，才可将 `review_status` 标为 `fallback_complete`；“查不到”不得转换成“没有股东/没有风险”。
