import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const runtimeModules = process.env.REPORT_NODE_MODULES;
const runtimeRequire = runtimeModules ? createRequire(path.join(runtimeModules, "..", "report-svg-runtime.cjs")) : createRequire(import.meta.url);
const { chromium } = runtimeRequire("playwright");
const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error("Usage: node render_svg_png.mjs <chart.svg> <chart.png>");
const browser = await chromium.launch(process.env.REPORT_CHROME_EXECUTABLE ? { executablePath: process.env.REPORT_CHROME_EXECUTABLE, headless: true } : { channel: "chrome", headless: true });
try {
  const svg = fs.readFileSync(input, "utf8");
  const page = await browser.newPage({ viewport: { width: 1200, height: 760 }, deviceScaleFactor: 2 });
  await page.setContent(`<html><body style="margin:0;background:#fff">${svg}</body></html>`);
  await page.locator("svg").screenshot({ path: output });
} finally { await browser.close(); }
