import path from "node:path";
import { createRequire } from "node:module";

// Node ESM does not use NODE_PATH.  Resolve Playwright from the optional
// runtime node_modules directory so the renderer remains portable.
const runtimeModules = process.env.REPORT_NODE_MODULES;
const runtimeRequire = runtimeModules
  ? createRequire(path.join(runtimeModules, "..", "report-pdf-runtime.cjs"))
  : createRequire(import.meta.url);
const { chromium } = runtimeRequire("playwright");

const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error("Usage: node render_report_pdf.mjs <report.html> <report.pdf>");
let browser;
try {
  browser = await chromium.launch(
    process.env.REPORT_CHROME_EXECUTABLE
      ? { executablePath: process.env.REPORT_CHROME_EXECUTABLE, headless: true }
      : { channel: "chrome", headless: true },
  );
} catch (error) {
  throw new Error(
    `无法启动 Chromium。请设置 REPORT_CHROME_EXECUTABLE，或安装 Chrome。原始错误：${error.message}`,
  );
}
try {
  const page = await browser.newPage();
  await page.goto(`file:///${path.resolve(input).replace(/\\/g, "/")}`, { waitUntil: "networkidle" });
  // The document stylesheet owns the page number through @page. Enabling a
  // browser footer here would print a second number on every page.
  await page.pdf({ path: output, format: "A4", printBackground: true, margin: { top: "18mm", right: "16mm", bottom: "18mm", left: "18mm" }, displayHeaderFooter: false });
} finally {
  await browser.close();
}
console.log(output);
