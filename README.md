# 项目前期评估 Skill

面向三亚中央商务区招商前期研判的可移植 Codex Skill。输入企业名称后，按上市/非上市路径完成企业研究、股权与财务核验、鼓励类产业目录判断、三亚承接分析和海南岛内实时政策匹配，默认交付 HTML，可选 PDF 或 Word。

## 安装

完整克隆或下载本仓库到 Agent 的 Skill 目录，保持目录名为 `project-preliminary-assessment`。不要只复制 `SKILL.md`。仓库不提供可直接渲染的真实企业示例；维护测试夹具仅位于 `tests/fixtures`，公开渲染入口会拒绝夹具数据，不能将其作为企业项目或交付报告。

首次安装或依赖变化后，在仓库根目录运行一次（仅安装依赖并验证浏览器，不跑完整发布测试）：

```powershell
& <python-path> -X utf8 scripts/ppa.py setup
```

仅需 Word 导出时使用 `--with-word`。日常生成报告不再重复安装依赖或运行发布测试。

PDF 证据正文提取首次需要 `pypdf`；若当前 Python 缺少它，请由操作者显式安装一次：

```powershell
& <python-path> -m pip install pypdf
```

`collect-web` 不会自动执行 pip；依赖缺失时会保留原始 PDF 并在证据记录中提示上述安装项。

已有项目遇到兼容版本更新时，执行 `ppa.py resume --work-dir work/company`，保留资料后重新准备、编译和核验，无需新建企业工作区。来源超过24小时仍需实时复验。

## 最短运行路径

```powershell
& <python-path> -X utf8 scripts/ppa.py start "企业法律全称" --work-dir work/company
# 在 enterprise-findings.json.research.enterprise_profile 中确认主体及 listed/nonlisted 路由
& <python-path> -X utf8 scripts/ppa.py research-plan --work-dir work/company
# 按该计划完成 enterprise-findings.json，并完成企业三台账、目录判断和三亚落地路径
& <python-path> -X utf8 scripts/ppa.py prepare-enterprise --work-dir work/company
# 真实官方扫描回执和候选草稿；不自动确认资格或有效性
& <python-path> -X utf8 scripts/ppa.py discover-policies --work-dir work/company
# 填写唯一政策主记录 policy_records 后
& <python-path> -X utf8 scripts/ppa.py compile --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py finalize --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company
```

`prepare-enterprise` 不依赖政策输入，成功后进入 `landing_businesses_complete`。`discover-policies` 保存真实回执、候选和正文/附件 evidence 草稿，不自动判定资格或有效性；`finalize` 集中报告独立错误，只有全成功才写 `report_ready` 和最终哈希。PDF 和 Word 分别在最后一条命令增加 `--pdf` 或 `--word`。

## 运行边界

- 上市公司以最新年度报告为集中主资料；非上市公司按企业官方材料、政府经营记录和合作方正式披露的固定路径查验。
- 政策必须实时核验海南省级、驻琼执行机构和三亚市级官方来源；国家政策只作背景，外省及海南其他地区专属政策不列为可享受政策。
- 企查查、天眼查不是强制依赖；只有当前 Agent 合法可访问页面或用户提供可验证导出材料时才作为补充。
- 全部文本和 JSON 使用 UTF-8。路径不得写死用户名、盘符、浏览器或 Python 安装位置。
- 目录阶段固定读取现有 Excel 与同源 JSON 的唯一内置库；匹配阶段引用 `catalog_entry_id` 与0基索引 `detail_index`，单个 detail 可默认 `0`，多个 detail 必须明确选择，程序派生原文条号，后续只引用派生结果，不重复读取整库。AI判断经营行为和技术条件；保留版本和官方出处。本地库不冒充实时政策有效，发现官方变更时提示更新，不自动无证改库。
- 企业主资料使用 `enterprise-findings.json.research.enterprise_profile`；顶层 `equity` 与 `policy_records` 分别是唯一主记录，报告和台账由编译派生。真实搜索/角色回执独立保留，不能从政策存在推断搜索完成。旧契约只经显式迁移，冲突不得静默选择。

业务规则以 [SKILL.md](SKILL.md) 为准，Agent 执行入口和禁止事项见 [AGENTS.md](AGENTS.md)。
