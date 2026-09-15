# 业务触发的实时政策检索

## 目的与时效

政策检索必须从已确认的企业事实、相邻经营活动和三亚落地业务出发，不能用固定政策清单反向虚构业务，也不能把一次网页失败写成“没有政策”。

每轮正式报告都要在 `policy-search-ledger.json` 写入带时区的 `researched_at` 和 `search_mode: realtime`，并与 `report-data.json.meta.policy_researched_at` 完全一致。报告超过24小时未交付时，重新核验正式原文、有效状态和当前申报或办理状态。只有发布测试使用的固定夹具可以跳过时间窗口。

## 业务语义展开

先完成 `policy_opportunity_radar`，再为每项可承接业务建立 `landing_business_hypotheses`，记录：

- 企业事实编号；
- 经营动作、企业角色、活动载体和预期贡献；
- 需要路由或明确排除的政府管理事项；
- 可能涉及的税收、资金、认定、账户、备案或办理工具。

按照“企业事实—相邻经营活动—政府事项—主管部门—政策工具”展开。相邻活动必须能回溯到企业事实，不得根据海南已有政策创造企业没有的业务。每个观察到的事实信号都要在机会雷达中获得展示、合并、排除、失效、待补证或检索未完成处置。

## 主管部门路由与检索路径

优先使用 `references/department-routing.json`。陌生复合业务可以依据部门职责、权责清单或正式文件建立本项目动态路由，但不得自动改写通用路由表。

每条部门检索记录必须写明角色和 `routing_basis`。角色只能为：

- `primary_regulator`
- `funding_authority`
- `co_issuer`
- `application_authority`
- `execution_authority`
- `provincial_counterpart`
- `municipal_counterpart`

检索路径按部门角色触发，不再要求所有部门机械完成七条路径：

| 适用对象 | 必需路径 |
| --- | --- |
| 所有主管部门 | `theme_search`、`department_documents`、`normative_documents`、`invalidity_catalog` |
| `primary_regulator` | 另查 `application_notices` |
| `funding_authority` | 另查 `application_notices`、`award_publicity` |
| `application_authority`、`execution_authority` | 另查 `application_notices` |
| `co_issuer`、省市协同部门 | 无额外路径 |

`document_graph` 是找到候选政策后追溯原文、实施细则、办理指南和关联文件的方法，不是每个部门都必须重复执行的独立证据路径。非资金主管部门不强制检索奖补公示。可以记录额外路径，但额外路径失败不替代本角色必需路径的完成状态。

每条回执只能为：

- `complete`：记录具体官方入口、检索词、检查时间、回执编号、结果数量、来源编号、证据编号和摘要；
- `not_available`：写明该部门不发布此类材料或官方路径不存在的依据；
- `failed` / `partial`：本角色必需路径出现该状态时，必须标记 `research_incomplete` 并停止交付。

主管部门首页不能代替文件目录或具体检索入口。新闻、规划、行动方案和招商宣传只用于发现线索，不能替代正式政策原文。

## 受控批量发现

完成落地业务和主管部门路由后，可通过唯一公开入口生成非破坏性的政策发现草案：

```powershell
& $py -X utf8 scripts/ppa.py discover-policies --work-dir work/company
```

该命令在 `work/company/evidence/policy-discovery/` 保存抓取证据，并把机器生成的部门扫描档案合并到 `policy-findings.json`；不会直接覆盖五份正式台账。相同部门和入口全报告只抓取一次，多个业务通过 `profile_id` 复用同一回执。机器未能完成的角色路径保留为 `partial`，Agent只补这些缺口，并定位政策原文、实施细则、申报通知和效力依据；完成后由 `ppa.py compile` 生成正式台账。

同一部门同一入口每轮只请求一次；不同官方域名最多并发4路，同域名并发1路。429、502、503、504最多退避重试2次。登录、验证码、403和付费墙不得绕过。缓存只有在本轮重新访问官方来源并留下复验回执后才可使用；动态申报通知、失效目录和公示必须重新获取。

## 结论边界

- 发现现行政策但企业资格尚缺事实：`conditional_opportunity`；
- 已核验企业不满足现行政策条件：`not_applicable`；
- 没有企业事实触发该事项：`not_triggered`；
- 本角色必需路径、政策附件或正式原文未完成：`research_incomplete`，停止交付；
- 所有相关部门的角色必需路径完成且没有现行候选政策：`no_current_policy`。

不得以资格未知、附件无法取得、网页失败或缓存过期替代 `no_current_policy`。只有现行、已纳入并取得正式来源的候选政策可以进入正式政策表；过期、续期不明、排除和待补证内容只留后台。

完成正式台账后只运行：

```powershell
& $py -X utf8 scripts/ppa.py advance --work-dir work/company
```

控制器会按当前状态连续执行全部已满足门禁，并停在第一个缺失阶段；不得直接调用内部校验器形成另一套流程。
