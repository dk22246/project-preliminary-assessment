# HTML、PDF与可选Word交付

企业研究完成后先生成 UTF-8 `report-data.json`。HTML、PDF和可选Word只能读取同一数据文件，不得分别重新写事实、政策或结论。

- 默认只生成 HTML。用户明确要求 PDF 时，才由最终 HTML 渲染 PDF；用户明确要求可编辑文件时，才从同一份数据生成 Word。
- HTML 使用 `references/html-templates.md` 的统一主题组件、A4打印规则、可跳转目录、来源超链接和程序生成的 SVG 股权图。默认采用 `sanya-cbd-editorial`；模板仅改变视觉呈现，不得改变同源数据事实。
- PDF 使用 `scripts/render_report_pdf.mjs` 通过 Playwright/Chromium 从最终 HTML 输出；浏览器路径可通过 `REPORT_CHROME_EXECUTABLE` 配置，未配置时由 Playwright 的 `chrome` 通道发现本机浏览器。
- Word 使用 `scripts/render_report_word.py`，保持同一八部分目录和数据字段；股权图以 SVG 插入，不使用浮动文本框。
- 运行 `scripts/validate_text_quality.py`、`scripts/validate_report_data.py` 后才能交付。PDF和HTML需再做文本一致性及页面渲染检查。
