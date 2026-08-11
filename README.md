# 项目前期评估 Skill

面向三亚中央商务区招商人员的企业尽调、三亚落地研判和海南岛内正式政策匹配 Skill。

## 使用范围

- 确认企业主体，研究业务、财务、风险与既有政府资源；
- 从企业事实信号中识别适合在三亚承接的总部、贸易、结算、品牌、渠道、供应链或投资活动，并动态展开政策机会；
- 只匹配海南省、三亚市或三亚中央商务区的正式现行政策；
- 默认生成固定七部分结构的 HTML《招商项目整体落地研判报告》，按需转换 PDF 或可编辑 Word。

## 关键约束

- 政策由企业事实信号和合理相邻经营活动触发，不得反向虚构业务；
- 外省政策、海南省内非三亚区域专属政策、过期或非正式政策不得写为可享受权益；
- 每项已确认业务和主管部门须完成七路径动态检索；网页、目录或相关附件未完成即阻断正式报告，不得写成“无政策”；
- 报告采用统一 HTML 模板；股权比例闭合到100%，行业位置必须证据化，政策表只显示“匹配政策或工具、匹配原因”；Word 为可选交付；
- 政策卡须通过 `scripts/validate_policy_scope.py` 校验；动态政策检索须通过 `scripts/validate_policy_search_coverage.py` 校验。

## 目录

- `SKILL.md`：运行逻辑与硬约束；
- `references/`：企业证据、政策范围、报告模板与 HTML/PDF/Word 交付规范；
- `scripts/`：数据校验、HTML 主渲染器以及可选 PDF/Word 转换器；
- `tests/`：业务触发逻辑和政策范围校验测试；
- `agents/openai.yaml`：Skill 元数据。

## 首次安装或版本升级

```powershell
python -X utf8 scripts/bootstrap.py --node <Node可执行文件路径>
```

默认运行 `scripts/run_report_pipeline.py <report-data.json> --equity-evidence <equity-evidence.json> --research-ledger <research-ledger.json> --policy-search-ledger <policy-search-ledger.json> --out-dir <目录> --node <node路径>` 生成 HTML，并强制通过股权证据及浏览器全页版式门禁。需要 PDF 时增加 `--pdf`；需要 Word 时增加 `--word`。Word 由 `scripts/render_report_word.py` 调用统一构建器处理版式、目录、页码和表格。

## 跨 Agent 部署

完整克隆仓库，不要仅复制 `SKILL.md`。安装 Node.js、Google Chrome/Chromium 后，在 Skill 根目录安装浏览器依赖（已有 Agent 随附 Playwright 时可跳过）：

```text
npm install
python -X utf8 scripts/bootstrap.py --node <Node可执行文件路径>
```

`bootstrap.py` 会记录关键文件指纹和真实运行时路径。首次安装或版本变化时执行完整预检和离线测试；同一版本再次调用只复用验证结果，不重复跑整套测试。正常报告前只运行 `scripts/doctor.py --node <Node路径>`，主流水线也会自动做同一快速检查。缺少浏览器、Playwright、网络或政策证据时直接报出准确缺项，不会静默降级。

政策结论不能缓存：每家企业、每次报告均须实时核验官方原文、有效状态和申报状态。允许复用官方入口注册表、同一轮检索结果和已下载原文，禁止把历史“可适用”结论直接搬到新报告。

维护者发布前才运行 `python -X utf8 scripts/verify_skill.py --release`；需要额外跑飞科HTML冒烟时使用 `--smoke`。不要在每个新会话或每家公司前运行完整测试。

若需要Word，另安装 `python -m pip install -r requirements-word.txt`。所有正式交付必须从 `report-data.json`、`equity-evidence.json`、`research-ledger.json` 和 `policy-search-ledger.json` 运行 `scripts/run_report_pipeline.py` 生成。
