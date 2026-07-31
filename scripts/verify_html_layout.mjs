import path from "node:path";
import { createRequire } from "node:module";

const runtimeModules = process.env.REPORT_NODE_MODULES;
const runtimeRequire = runtimeModules
  ? createRequire(path.join(runtimeModules, "..", "report-layout-runtime.cjs"))
  : createRequire(import.meta.url);
const { chromium } = runtimeRequire("playwright");

const [input] = process.argv.slice(2);
if (!input) throw new Error("Usage: node verify_html_layout.mjs <report.html>");

const fileUrl = `file:///${path.resolve(input).replace(/\\/g, "/")}`;
let browser;
try {
  browser = await chromium.launch(
    process.env.REPORT_CHROME_EXECUTABLE
      ? { executablePath: process.env.REPORT_CHROME_EXECUTABLE, headless: true }
      : { channel: "chrome", headless: true },
  );
} catch (error) {
  throw new Error(`无法启动 Chromium 进行版式验收：${error.message}`);
}

try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  await page.goto(fileUrl, { waitUntil: "networkidle" });
  const errors = await page.evaluate(() => {
    const errors = [];
    if (document.documentElement.scrollWidth > document.documentElement.clientWidth + 1) {
      errors.push("页面出现横向越界");
    }
    for (const table of document.querySelectorAll(".report-table")) {
      const label = table.closest("section")?.id || "报告表格";
      if (table.scrollWidth > table.clientWidth + 1) {
        errors.push(`${label}：报告表格出现横向滚动或越界`);
      }
      for (const cell of table.querySelectorAll("th, td")) {
        // Browsers can report a one-pixel scroll-height difference for a
        // border-box with fractional line-height. Two pixels still catches
        // real clipping while avoiding that rendering-rounding false positive.
        if (cell.scrollWidth > cell.clientWidth + 2 || cell.scrollHeight > cell.clientHeight + 2) {
          errors.push(`${label}：表格单元格文本溢出（${cell.textContent.trim().slice(0, 24)}）`);
        }
      }
      for (const row of table.rows) {
        for (let index = 1; index < row.cells.length; index += 1) {
          const previous = row.cells[index - 1].getBoundingClientRect();
          const current = row.cells[index].getBoundingClientRect();
          if (previous.right > current.left + 1) {
            errors.push(`${label}：相邻表格单元格发生重叠`);
          }
        }
      }
    }
    for (const svg of document.querySelectorAll(".svg-wrap svg")) {
      const wrapper = svg.closest(".svg-wrap");
      const svgRect = svg.getBoundingClientRect();
      const wrapperRect = wrapper.getBoundingClientRect();
      if (svgRect.right > wrapperRect.right + 1 || svgRect.left < wrapperRect.left - 1) {
        errors.push("股权图 SVG 容器越出画布面板");
      }
      const viewBox = svg.viewBox.baseVal;
      const textBounds = [];
      for (const element of svg.querySelectorAll("rect, line, text")) {
        const bounds = element.getBBox();
        if (bounds.x < -1 || bounds.y < -1 || bounds.x + bounds.width > viewBox.width + 1 || bounds.y + bounds.height > viewBox.height + 1) {
          errors.push(`股权图元素越出 SVG 画布（${element.tagName.toLowerCase()}）`);
        }
        if (element.tagName.toLowerCase() === "text") textBounds.push(bounds);
      }
      for (let index = 1; index < textBounds.length; index += 1) {
        for (let previous = 0; previous < index; previous += 1) {
          const a = textBounds[previous];
          const b = textBounds[index];
          if (Math.min(a.x + a.width, b.x + b.width) > Math.max(a.x, b.x) + 1 && Math.min(a.y + a.height, b.y + b.height) > Math.max(a.y, b.y) + 1) {
            errors.push("股权图 SVG 文本发生重叠");
          }
        }
      }
    }
    return errors;
  });
  if (errors.length) throw new Error(errors.join("\n"));
  console.log("通过：浏览器页面、全部报告表格和股权图均无越界、溢出或重叠");
} finally {
  await browser.close();
}
