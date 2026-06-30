#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");

const rootDir = path.resolve(__dirname, "..");
const staticDir = path.join(rootDir, "static");
const appDir = path.join(staticDir, "app");
const indexPath = path.join(staticDir, "index.html");
const generatedBundlePath = path.join(staticDir, "app.js");
const failures = [];

function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}

function fail(message) {
  failures.push(message);
}

const indexHtml = readText(indexPath);
if (!/<script\s+type="module"\s+src="\/static\/app\/main\.js"\s*><\/script>/.test(indexHtml)) {
  fail("static/index.html must load /static/app/main.js as type=module");
}
if (/\/static\/app\.js/.test(indexHtml)) {
  fail("static/index.html must not load the generated /static/app.js bundle");
}
if (fs.existsSync(generatedBundlePath)) {
  fail("static/app.js should not exist; the browser loads source modules directly");
}

const moduleFiles = fs.readdirSync(appDir)
  .filter((name) => name.endsWith(".js"))
  .sort();

for (const fileName of moduleFiles) {
  const filePath = path.join(appDir, fileName);
  const relativePath = `static/app/${fileName}`;
  const text = readText(filePath);
  if (/\bwindow\.OJApp\b|\bOJApp\b/.test(text)) {
    fail(`${relativePath} must not use the old OJApp global registry`);
  }
  if (/^\s*\(function\s*\(\)\s*\{/.test(text)) {
    fail(`${relativePath} must not use the old IIFE bundle wrapper`);
  }
  if (/\son[a-z]+\s*=/.test(text)) {
    fail(`${relativePath} must not use inline DOM event attributes`);
  }
  const importPattern = /import\s+(?:[\s\S]*?)\s+from\s+["']([^"']+)["'];/g;
  for (const match of text.matchAll(importPattern)) {
    const importPath = match[1];
    if (!importPath.startsWith("./")) {
      fail(`${relativePath} imports ${importPath}; only local ./ imports are allowed`);
      continue;
    }
    if (!importPath.endsWith(".js")) {
      fail(`${relativePath} imports ${importPath}; browser module imports must include .js`);
      continue;
    }
    const targetPath = path.resolve(appDir, importPath);
    if (!targetPath.startsWith(appDir + path.sep) || !fs.existsSync(targetPath)) {
      fail(`${relativePath} imports missing module ${importPath}`);
    }
  }
}

if (!moduleFiles.includes("main.js")) {
  fail("static/app/main.js is required as the browser module entrypoint");
}

if (failures.length) {
  failures.forEach((message) => process.stderr.write(`frontend module check failed: ${message}\n`));
  process.exit(1);
}

process.stdout.write(`Frontend module check passed for ${moduleFiles.length} modules.\n`);
