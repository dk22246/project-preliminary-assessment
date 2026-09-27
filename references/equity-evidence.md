# 股权网页取证与证据门禁

## 核心原则

输入阶段以顶层 `equity` 作为唯一股权主记录；节点使用稳定 `key`，连接线引用节点 `key`。编译器从该记录派生报告股权视图和本证据台账，避免 AI 重复抄写；本文件以下证据、断言、时点、哈希和冲突门禁仍然适用。

股权图只呈现有证据的节点和连线。先锁定准确法律主体、统一社会信用代码和登记状态，再查询股东；不得用品牌名、集团简称或证券简称拼接不同主体的数据。

法定披露优先：上市公司以交易所公告、年度报告、招股说明书和控制权变更公告等法定披露定案。企查查和天眼查对上市、非上市两条路线均不是强制入口；商业平台只有在用户提供可验证导出材料，或当前Agent确有合法可访问页面时才作为可选差异复核来源。非上市公司优先使用公开登记、企业正式材料、政府监管、许可备案、司法文书等可定位来源核验股权；商业平台不可访问时不再制造失败回执。

## 上市公司法定披露路径

1. 使用最新年度报告确认控股股东、实际控制人、直接股东比例、主要子公司和数据时点；
2. 仅在最新年报存在历史缺口或控制权变化时，定向检查招股说明书、以前年度对应章节及控制权变更公告；
3. 将法定披露直接登记为 `legal_disclosure` 来源，每个股权节点和连接线绑定来源编号、断言类型与数据时点；
4. `provider_attempts` 可以为空，但必须存在至少一项成功的 `legal_disclosure` 来源；
5. 不得为了生成商业平台回执而访问登录页、搜索结果摘要或无法定位到准确主体的页面。

## 可选网页取证顺序

1. 仅在当前路线需要商业平台，或用户提供了可验证材料时，Agent 使用其已有合法浏览器登录态访问企查查网页，按准确法律主体检索企业详情页，记录法律全称、统一社会信用代码、登记状态、当前股东、页面显示的持股比例、实际控制人或受益人标记、历史股东或历史变更、主要子公司、数据时点、页面 URL 和页面内定位。
2. Agent 使用同样方法访问天眼查网页进行复核。不得绕过登录、验证码、付费墙、订阅等级或其他访问控制；Cookie、会话信息和账户信息不得写入 Skill、命令或证据文件。
3. 每个平台的可见结果分别保存为符合 `schemas/equity-web-capture.schema.json` 的标准化 JSON，并运行：

```powershell
& $py -X utf8 scripts/ppa.py collect-equity "法律主体" --provider qcc-web --input-json qcc-capture.json --out-dir evidence/qcc
& $py -X utf8 scripts/ppa.py collect-equity "法律主体" --provider tianyancha-web --input-json tianyancha-capture.json --out-dir evidence/tianyancha
```

4. 每次成功采集必须同时生成 `provider-query-bundle.json` 和 `normalized-equity-fragment.json`。后者至少包含 `provider`、`legal_entity`、`source`、`nodes`、`edges`、`captured_at`；每个节点和连线必须携带来源编号、断言类型、数据时点和页面内定位。
5. 页面不可访问、登录态失效、验证码、付费限制、页面字段缺失或主体不一致时，保留真实原因，不得改写为成功或“无股东”。随后使用法定披露或官方登记补证。

## 标准化记录

网页取证 JSON 的 `records` 使用以下 `record_type`：

- `current_shareholder`：当前股东；`shareholding_ratio` 字段必须存在，页面未显示时固定填写“页面未披露”，不得估算或补猜。
- `actual_controller`、`beneficial_owner`：仅按页面显示记录。若来自平台穿透或算法推算，`assertion_type` 必须为 `provider_calculation`，`relationship` 必须带“推定”“疑似”或“平台穿透”。
- `historical_shareholder`、`historical_change`：记录历史股东或变更事实及对应时点。
- `subsidiary`：页面显示的主要子公司或对外投资主体；不能由名称相似推断控制关系。

输入缺少 `page_url`、`captured_at`、`legal_entity`、非空 `records`，或网页主体与命令锚点不一致时，采集器必须失败。`qcc_web` 只接受 `https://qcc.com` 及其子域，`tianyancha_web` 只接受 `https://tianyancha.com` 及其子域。

每次网页取证必须在 `coverage_dispositions` 对 `company_identity`、`current_shareholder`、`controller_or_beneficial_owner`、`historical_change`、`major_subsidiary` 逐项写明 `captured`、`not_disclosed` 或 `inaccessible`。主体身份和当前股东必须 `captured`；其余三类未捕获时必须给出真实 `reason`，不得静默遗漏。

## 报告与台账门禁

归一化 fragment 只作为后续合并输入，不会自动升级为最终结论。合并后的 `equity-evidence.json` 必须符合 `schemas/equity-evidence.schema.json`，并至少记录：

- 精确法律主体及统一社会信用代码；
- 实际访问企查查或天眼查时才登记 `provider_attempts`；未访问时保持空数组，两条路由均不得为了通过门禁制造尝试回执；
- 每条成功网页来源的页面 URL、采集时间、记录数量、可定位位置及可验证的 `artifact_path`、`artifact_sha256`、`bundle_path`、`bundle_sha256`；CLI 从 `equity-evidence.json` 目录校验 capture 与 query bundle 的文件、哈希、主体、提供方、时点、URL 和记录数一致；
- 每个节点和连线的名称、关系、断言类型、数据时点和 `E` 类来源编号；
- 网页之间、网页与法定披露之间的冲突及处理状态。

报告 `equity.nodes` 和 `equity.edges` 的每一项都必须填写 `evidence_source_ids`。先运行：

```powershell
& $py -X utf8 scripts/ppa.py finalize --work-dir work/company
```

凡连接线展示持股比例，必须同时写入数值型 `ownership_percent`。`data_status=available` 时，同一被投资主体已展示的直接股东比例必须合计100%；无法可靠拆分剩余股东但同一可靠来源明确给出剩余合计时，才可使用“其他股东合计”节点补足。`data_status=partial` 时只画已核实的关系和比例，未知部分不得补造，连接线比例未知时须明确写“比例未公开”。

完成非上市固定来源阶梯后仍无法取得任何可靠股权关系时，`equity-evidence.json.review_status` 填 `not_public` 或 `inaccessible`，并记录 `availability_note`；报告 `equity.data_status` 使用同一状态、`nodes` 和 `edges` 保持空数组、`search_source_ids` 列出实际查验来源。此时HTML、PDF和Word均省略股权图，显示“股权公开信息不足”及需企业补充的材料，不阻断其他章节。不得用企业名称、自称集团关系、注册资本或平台搜索摘要生成占位股权图。

报告正文只显示“股权来源：资料名称（E编号），数据时点YYYY-MM-DD”。企查查、天眼查的尝试、失败原因、artifact和哈希全部保留在 `equity-evidence.json`，不在报告堆叠。只有存在实质来源差异时，才在图下显示“股权数据差异说明”。

## 断言边界

- `registry_fact`：网页明确显示的工商登记股东、登记持股比例或历史变更。
- `legal_disclosure`：年报、交易所公告或监管文件明确披露的控制关系。
- `consolidation_scope`：仅能证明并表或控制，持股比例未披露时不得补猜。
- `provider_calculation`：平台穿透或算法推算结果。不得把平台计算结果直接写成已确认的实际控制人；关系名称必须带“平台穿透推定”“疑似”或同等限定。

两家网页结果冲突、数据时点不一致或主体标识无法对齐时，必须写入 `conflicts`，不得静默选择其中一家，也不得用图形排版掩盖证据缺口。上市公司采用法定披露定案，但仍应披露网页差异及后续核实动作。

每项差异必须填写唯一 `C` 编号，以及差异字段、严重程度、处理状态、各方口径、可能原因、采用口径、招商影响、后续核实动作、图形处理方式、影响的节点或连线和 `E` 类来源编号。报告 `equity.conflict_disclosures` 必须逐项复制同一结构并通过一致性校验。

- `general`：比例尾差、更新时间、统计口径或历史/当前状态差异。保留确认部分，争议比例不绘制，`review_status` 设为 `qualified_complete`。
- `material_local`：局部股东、子公司或控制连接存在重要差异。将 `graph_action` 设为 `omit_disputed_part`，从股权图删除争议节点或连线后继续生成。
- `subject_critical`：法律主体或核心控制关系存在未解决冲突，足以导致分析混用。将 `review_status` 设为 `blocked`；法定披露定案后可改为 `resolved` 并说明差异。

## 降级规则

实际访问商业平台时，如受登录状态、验证码、付费限制、访问控制或页面故障影响，必须保留 `unavailable` 或 `error` 回执及真实原因，再使用法定披露或官方登记材料；未访问商业平台不属于降级。只有实际发起商业平台访问但失败、且替代来源能够逐节点、逐连线支撑报告股权图时，才可将 `review_status` 标为 `fallback_complete`。“未公开”只表示规定来源未取得可靠股权关系，不得转换成“没有股东/没有控制人”。
