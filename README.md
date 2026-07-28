# 项目前期评估 Skill

面向三亚中央商务区招商人员的企业尽调、三亚落地研判和海南岛内正式政策匹配 Skill。

## 使用范围

- 确认企业主体，研究业务、财务、风险与既有政府资源；
- 从企业真实业务中识别适合在三亚承接的总部、贸易、结算、品牌、渠道、供应链或投资功能；
- 只匹配海南省、三亚市或三亚中央商务区的正式现行政策；
- 默认生成固定八部分结构的 HTML《招商项目整体落地研判报告》，按需转换 PDF 或可编辑 Word。

## 关键约束

- 政策由拟落地业务触发，不得反向虚构业务；
- 外省政策、海南省内非三亚区域专属政策、过期或非正式政策不得写为可享受权益；
- 报告采用统一 HTML 模板、可跳转目录、固定财务主表、政府补助明细表及来源编号；Word 为可选交付；
- 政策卡须通过 `scripts/validate_policy_scope.py` 校验。

## 目录

- `SKILL.md`：运行逻辑与硬约束；
- `references/`：企业证据、政策范围、报告模板与 HTML/PDF/Word 交付规范；
- `scripts/`：数据校验、HTML 主渲染器以及可选 PDF/Word 转换器；
- `tests/`：业务触发逻辑和政策范围校验测试；
- `agents/openai.yaml`：Skill 元数据。

## 本地验证

```powershell
python -m unittest discover -s tests -v
```

默认运行 `scripts/run_report_pipeline.py <report-data.json> --out-dir <目录>` 生成 HTML。需要 PDF 时增加 `--pdf --node <node路径>`；需要 Word 时增加 `--word --node <node路径>`。Word 由 `scripts/render_report_word.py` 调用统一构建器处理版式、目录、页码和表格。

## 跨 Agent 部署

完整克隆仓库，不要仅复制 `SKILL.md`。首次部署后，以 UTF-8 模式执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_utf8.ps1 scripts\preflight.py --smoke
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_utf8.ps1 -m unittest discover -s tests -v
```

预检会检查目录完整性、UTF-8 文本、示例数据和政策门禁，并用示例生成 HTML。上述 PowerShell 启动器同时固定终端和 Python 的 UTF-8 编码，并自动使用 `python` 或 `py -3`；两者都不在 PATH 时，可增加 `-Python C:\path\to\python.exe` 或设置 `SKILL_PYTHON`。任一命令失败时，不应生成正式报告。所有正式交付必须从 `report-data.json` 运行 `scripts/run_report_pipeline.py` 生成；PDF 和 Word 均为按需转换。
