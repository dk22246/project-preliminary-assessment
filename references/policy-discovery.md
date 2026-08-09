# 主管部门路由与候选政策发现

先将企业事实信号展开为可合理相邻的经营活动，再拆成政府管理事项并路由主管部门；禁止用“行业名称 → 某项补贴”的捷径，也禁止只等待企业明确提出落地意图。相邻活动不是虚构业务，必须能回溯到事实来源并在机会雷达中逐项处置。

优先使用 `references/department-routing.json` 的通用事项—部门—主题关系。陌生复合业务由模型拆成多个管理事项；静态表没有时，必须以部门职责、权责清单或正式文件建立本项目动态路由，记录职责来源。动态路由不得自动写回通用表。

每个已确认主管部门必须在 `policy-search-ledger.json` 留下七条检索回执：`theme_search`、`department_documents`、`normative_documents`、`application_notices`、`award_publicity`、`invalidity_catalog`、`document_graph`。每条回执要么完成并留下具体官方入口、回执编号和结果摘要，要么以 `not_available` 写明官方依据；`failed` 或 `partial` 一律为 `research_incomplete`，不得输出正式报告。主管部门首页不能代替部门文件目录扫描。

同一部门在多个政策主题中可复用同一份已完成的部门检索回执档案，但档案必须属于该部门并完整包含七条路径。网页采集、浏览器、搜索工具和人工检索只是在取得回执的方式上不同，不能改变台账字段或绕过校验。新闻、规划和公示只能发现线索，不能替代正式原文。

候选政策使用 `current_open`、`current_no_open_call`、`current_conditional`、`expired_relevant`、`renewal_pending`、`not_applicable`、`insufficient_evidence` 状态。发现现行政策而企业资格缺少事实时，报告结论必须为 `conditional_opportunity`；已确认不符合条件才是 `not_applicable`；无业务事实触发才是 `not_triggered`。只有在全部相关部门七路径完成且未发现现行候选时，才可使用 `no_current_policy`。只有现行且已纳入的候选政策，才能支撑正式报告的政策卡；过期或续期不明政策只能作为历史参考或核验事项。
