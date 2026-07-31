# 动态政策检索覆盖台账

## 目的

将“发现业务”与“确认没有政策”之间的检索过程变成可校验记录。不得把网页搜索结果、单个新闻、主管部门首页或采集工具失败，写成“未发现政策”。

## 先做业务语义展开

对每项拟落地业务建立一条 `landing_business_hypotheses`，至少写入：

- `fact_ids`：企业公开事实；
- `actions`、`roles`、`forms`、`effects`；
- `government_matters`：每项必须 `route` 到已有路由，或 `exclude` 并写明依据；
- `policy_instruments`：可能的税收、资金、认定、便利、账户、备案或奖励工具。

按事实层、上位事项层、相邻事项层三轮展开。示例：企业“主办电竞嘉年华”不能只检索“电竞”，还应展开为体育赛事、大型活动、文化旅游、消费促进等管理事项，并由部门职责和正式路由决定是否纳入。

## 部门角色和七路径

每个 `department_searches` 必须记录一个角色：`primary_regulator`、`funding_authority`、`co_issuer`、`application_authority`、`execution_authority`、`provincial_counterpart` 或 `municipal_counterpart`，以及 `routing_basis`。

每个已确认部门必须逐条记录以下 `runs`：

1. `theme_search`
2. `department_documents`
3. `normative_documents`
4. `application_notices`
5. `award_publicity`
6. `invalidity_catalog`
7. `document_graph`

每条回执只能为：

- `complete`：必须有具体官方入口地址、回执编号和结果摘要；目录扫描不得只填主管部门首页。
- `not_available`：必须写明官方路径不存在或该部门不发布该类材料的依据。
- `failed` / `partial`：自动将该搜索任务视为 `research_incomplete`，不得生成正式报告。

`collect_web_evidence.py` 只负责网页和附件取证；它不是完整的政策发现器。无论使用浏览器、搜索引擎、网页采集器还是人工目录检索，结果都必须写入同一份 `policy-search-ledger.json`。

## 结论状态边界

- 发现现行政策、企业资格尚缺事实：`conditional_opportunity`。
- 发现现行政策、已确认企业不满足条件：`not_applicable`。
- 没有业务事实触发该事项：`not_triggered`。
- 路径、附件或目录检索未完成：`research_incomplete`，停止交付。
- 仅在所有相关部门七路径完成且无现行候选政策时：`no_current_policy`。

不得用企业资格不明、附件无法取得或网页访问失败来替代 `no_current_policy`。

## 校验

```powershell
& $py -X utf8 scripts/validate_policy_search_coverage.py policy-search-ledger.json --research-ledger research-ledger.json --report-data report-data.json
```

正式流水线必须传入 `--policy-search-ledger policy-search-ledger.json`。校验失败时，不得生成 HTML、PDF 或 Word。
