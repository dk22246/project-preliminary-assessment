# HTML、PDF与可选Word交付

企业研究完成后先生成 UTF-8 `report-data.json`。HTML、PDF和可选Word只能读取同一数据文件，不得分别重新写事实、政策或结论。

- 默认只生成 HTML。用户明确要求 PDF 时，才由最终 HTML 渲染 PDF；用户明确要求可编辑文件时，才从同一份数据生成 Word。
- HTML 使用 `references/html-templates.md` 的统一主题组件、A4打印规则、可跳转目录、来源超链接和程序生成的 SVG 股权图。默认采用 `sanya-cbd-editorial`；模板仅改变视觉呈现，不得改变同源数据事实。
- PDF 使用 `scripts/render_report_pdf.mjs` 通过 Playwright/Chromium 从最终 HTML 输出；浏览器路径可通过 `REPORT_CHROME_EXECUTABLE` 配置，未配置时由 Playwright 的 `chrome` 通道发现本机浏览器。
- Word 使用 `scripts/render_report_word.py`，保持同一八部分目录和数据字段；股权图以 SVG 插入，不使用浮动文本框。
- 所有报告表格必须在渲染前校验“每行列数 = 表头列数、列宽数量 = 表头列数、列宽合计 = 100%”；不一致即停止渲染。财务表必须从 `meta.financial_currency` 与 `meta.financial_unit` 动态生成表头；收入和利润单元格只显示数值，同比单元格只显示短值，说明以表下注释显示。不得把年度说明放进窄列，也不得将任何财务列文字强制单行。
- `scripts/run_report_pipeline.py` 必须提供 `--node`，并会自动运行 `scripts/verify_html_layout.mjs`。门禁检查整页横向宽度、全部报告表格的滚动/文本/单元格重叠、SVG 容器与元素边界，以及 SVG 文本互相重叠；失败时禁止生成 PDF 或 Word。PDF和Word需再做文本一致性及页面渲染检查。
