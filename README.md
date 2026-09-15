# 项目前期评估 Skill

面向三亚中央商务区招商前期研判的可移植 Codex Skill。输入企业名称后，按上市/非上市路径完成企业研究、股权与财务核验、鼓励类产业目录判断、三亚承接分析和海南岛内实时政策匹配，默认交付 HTML，可选 PDF 或 Word。

## 安装

完整克隆或下载本仓库到 Agent 的 Skill 目录，保持目录名为 `project-preliminary-assessment`。不要只复制 `SKILL.md`，也不要复制 `examples` 作为企业项目。

首次安装或更新版本后，在仓库根目录运行一次：

```powershell
& <python-path> -X utf8 scripts/ppa.py setup
```

仅需 Word 导出时使用 `--with-word`。日常生成报告不再重复安装依赖或运行发布测试。

## 最短运行路径

```powershell
& <python-path> -X utf8 scripts/ppa.py start "企业法律全称" --work-dir work/company
# 在 enterprise-findings.json 中确认主体及 listed/nonlisted 路由
& <python-path> -X utf8 scripts/ppa.py research-plan --work-dir work/company
# 按该计划完成 enterprise-findings.json；实时政策发现后完成 policy-findings.json
& <python-path> -X utf8 scripts/ppa.py discover-policies --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py compile --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py finalize --work-dir work/company
& <python-path> -X utf8 scripts/ppa.py deliver --work-dir work/company --out-dir outputs/company
```

`finalize` 是生成报告前唯一一次完整校验。PDF 和 Word 分别在最后一条命令增加 `--pdf` 或 `--word`。

## 运行边界

- 上市公司以最新年度报告为集中主资料；非上市公司按企业官方材料、政府经营记录和合作方正式披露的固定路径查验。
- 政策必须实时核验海南省级、驻琼执行机构和三亚市级官方来源；国家政策只作背景，外省及海南其他地区专属政策不列为可享受政策。
- 企查查、天眼查不是强制依赖；只有当前 Agent 合法可访问页面或用户提供可验证导出材料时才作为补充。
- 全部文本和 JSON 使用 UTF-8。路径不得写死用户名、盘符、浏览器或 Python 安装位置。

业务规则以 [SKILL.md](SKILL.md) 为准，Agent 执行入口和禁止事项见 [AGENTS.md](AGENTS.md)。
