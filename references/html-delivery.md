# HTML、PDF与可选Word交付

企业研究完成后先生成 UTF-8 `report-data.json`。HTML、PDF和可选Word只能读取同一数据文件，不得分别重新写事实、政策或结论。

- 默认生成 HTML 与可编辑 Word（同一份数据）。PDF 由报告内“导出 PDF”按钮（浏览器打印）或用户明确要求时，才由最终 HTML 渲染。
- HTML 使用 `references/html-templates.md` 的统一主题组件、A4打印规则、可跳转目录、来源超链接和程序生成的 SVG 股权图。默认采用 `sanya-cbd-editorial`；模板仅改变视觉呈现，不得改变同源数据事实。
- PDF 使用 `scripts/render_report_pdf.mjs` 通过 Playwright/Chromium 从最终 HTML 输出；浏览器路径可通过 `REPORT_CHROME_EXECUTABLE` 配置，未配置时由 Playwright 的 `chrome` 通道发现本机浏览器。
- Word 由 `ppa.py deliver --word` 从同一数据生成，保持七部分目录和字段；流水线将股权SVG转为高分辨率PNG后嵌入，不使用浮动文本框。
- 所有报告表格必须在渲染前校验“每行列数 = 表头列数、列宽数量 = 表头列数、列宽合计 = 100%”；不一致即停止渲染。财务表必须从 `meta.financial_currency` 与 `meta.financial_unit` 动态生成表头；收入和利润单元格只显示数值，同比单元格只显示短值，说明以表下注释显示。不得把年度说明放进窄列，也不得将任何财务列文字强制单行。
- `scripts/ppa.py deliver` 强制绑定同一工作区的五份台账、`workflow-state.json` 和报告就绪哈希；报告就绪后不重复运行数据门禁，只进行同源渲染。HTML随后自动执行整页宽度、表格滚动/文本/单元格重叠、SVG容器和SVG文本重叠检查；失败时禁止生成PDF或Word。PDF由已验收HTML生成。Word执行结构与同源字段检查；只有运行环境具备LibreOffice或Word页面渲染能力时才做逐页图像复核，缺少该能力时必须在交付说明中明确。
