# 股权网页取证与证据门禁

## 核心原则

股权图只呈现有证据的节点和连线。先锁定准确法律主体、统一社会信用代码和登记状态，再查询股东；不得用品牌名、集团简称或证券简称拼接不同主体的数据。

法定披露优先：上市公司以交易所公告、年度报告、招股说明书等法定披露定案。企查查网页和天眼查网页用于主体锚定、工商股东、历史变化和差异复核；非上市公司的关键控制关系仍应尽量与国家企业信用信息公示系统、企业正式材料或监管文件交叉核验。

## 网页取证顺序

1. Agent 使用其已有合法浏览器登录态访问企查查网页，按准确法律主体检索企业详情页，记录法律全称、统一社会信用代码、登记状态、当前股东、页面显示的持股比例、实际控制人或受益人标记、历史股东或历史变更、主要子公司、数据时点、页面 URL 和页面内定位。
2. Agent 使用同样方法访问天眼查网页进行复核。不得绕过登录、验证码、付费墙、订阅等级或其他访问控制；Cookie、会话信息和账户信息不得写入 Skill、命令或证据文件。
3. 每个平台的可见结果分别保存为符合 `schemas/equity-web-capture.schema.json` 的标准化 JSON，并运行：

```powershell
& $py -X utf8 scripts/collect_equity_provider.py "法律主体" --provider qcc-web --input-json qcc-capture.json --out-dir evidence/qcc
& $py -X utf8 scripts/collect_equity_provider.py "法律主体" --provider tianyancha-web --input-json tianyancha-capture.json --out-dir evidence/tianyancha
```

4. 每次成功采集必须同时生成 `provider-query-bundle.json` 和 `normalized-equity-fragment.json`。后者至少包含 `provider`、`legal_entity`、`source`、`nodes`、`edges`、`captured_at`；每个节点和连线必须携带来源编号、断言类型、数据时点和页面内定位。
5. 页面不可访问、登录态失效、验证码、付费限制、页面字段缺失或主体不一致时，保留真实原因，不得改写为成功或“无股东”。随后使用法定披露或官方登记补证。

## 标准化记录

网页取证 JSON 的 `records` 使用以下 `record_type`：

- `current_shareholder`：当前股东；页面显示比例时原样记录，未显示时不创建比例字段。
- `actual_controller`、`beneficial_owner`：仅按页面显示记录。若来自平台穿透或算法推算，`assertion_type` 必须为 `provider_calculation`，`relationship` 必须带“推定”“疑似”或“平台穿透”。
- `historical_shareholder`、`historical_change`：记录历史股东或变更事实及对应时点。
- `subsidiary`：页面显示的主要子公司或对外投资主体；不能由名称相似推断控制关系。

输入缺少 `page_url`、`captured_at`、`legal_entity`、非空 `records`，或网页主体与命令锚点不一致时，采集器必须失败。比例缺失时保持缺失，不得估算、倒算或填入占位百分比。

## 报告与台账门禁

归一化 fragment 只作为后续合并输入，不会自动升级为最终结论。合并后的 `equity-evidence.json` 必须符合 `schemas/equity-evidence.schema.json`，并至少记录：

- 精确法律主体及统一社会信用代码；
- `qcc_web`、`tianyancha_web` 的本轮真实尝试状态、查询时间和失败原因；
- 每条来源的页面 URL、采集时间、记录数量和可定位位置；
- 每个节点和连线的名称、关系、断言类型、数据时点和 `E` 类来源编号；
- 网页之间、网页与法定披露之间的冲突及处理状态。

报告 `equity.nodes` 和 `equity.edges` 的每一项都必须填写 `evidence_source_ids`。先运行：

```powershell
& $py -X utf8 scripts/validate_equity_evidence.py equity-evidence.json --report-data report-data.json
```

只有本轮网页成功回执、成功来源和非空记录三者同时存在时，报告才能写“企查查网页已核验”或“天眼查网页已核验”。没有成功回执时必须说明真实失败原因和采用的法定披露或官方登记补证，不得声称已核验。

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

网页受登录状态、验证码、付费限制、访问控制或页面故障影响时，必须保留 `unavailable` 或 `error` 回执及真实原因，再使用法定披露或官方登记材料。只有替代来源能够逐节点、逐连线支撑报告股权图时，才可将 `review_status` 标为 `fallback_complete`；“查不到”不得转换成“没有股东/没有风险”。
