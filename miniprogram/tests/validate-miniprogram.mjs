import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

function readJson(file) {
  return JSON.parse(read(file));
}

function exists(file) {
  return fs.existsSync(path.join(root, file));
}

const requiredFiles = [
  'app.js',
  'app.json',
  'app.wxss',
  'project.config.json',
  'sitemap.json',
  'config.js',
  'services/api.js',
  'services/session.js',
  'utils/format.js',
  'utils/chart.js',
  'pages/login/index.js',
  'pages/login/index.json',
  'pages/login/index.wxml',
  'pages/login/index.wxss',
  'pages/dashboard/index.js',
  'pages/dashboard/index.json',
  'pages/dashboard/index.wxml',
  'pages/dashboard/index.wxss',
  'pages/news/index.js',
  'pages/news/index.json',
  'pages/news/index.wxml',
  'pages/news/index.wxss',
  'pages/paper/index.js',
  'pages/paper/index.json',
  'pages/paper/index.wxml',
  'pages/paper/index.wxss',
  'README.md',
];

for (const file of requiredFiles) {
  assert.ok(exists(file), `missing required mini program file: ${file}`);
}

const app = readJson('app.json');
const contentPages = ['pages/dashboard/index', 'pages/news/index', 'pages/paper/index'];
assert.equal(app.pages[0], 'pages/login/index', 'login page must be the mini program entry');
assert.deepEqual(app.pages.slice(1), contentPages);
assert.deepEqual(app.tabBar.list.map((item) => item.pagePath), contentPages);
assert.deepEqual(app.tabBar.list.map((item) => item.text), ['Dashboard', 'News', '模拟交易']);
for (const item of app.tabBar.list) {
  assert.ok(item.iconPath, `${item.pagePath} should define tabBar iconPath`);
  assert.ok(item.selectedIconPath, `${item.pagePath} should define tabBar selectedIconPath`);
  assert.ok(exists(item.iconPath), `missing tabBar icon: ${item.iconPath}`);
  assert.ok(exists(item.selectedIconPath), `missing selected tabBar icon: ${item.selectedIconPath}`);
}

for (const file of ['app.json', 'project.config.json', 'sitemap.json', 'pages/login/index.json', 'pages/dashboard/index.json', 'pages/news/index.json', 'pages/paper/index.json']) {
  assert.doesNotThrow(() => readJson(file), `${file} must be valid JSON`);
}

for (const file of requiredFiles.filter((item) => item.endsWith('.js'))) {
  const result = spawnSync(process.execPath, ['--check', path.join(root, file)], { encoding: 'utf8' });
  assert.equal(result.status, 0, `${file} must parse as JavaScript:\n${result.stderr}`);
}

const appStyle = read('app.wxss');
assert.ok(appStyle.includes('.ui-icon'), 'app.wxss should define reusable icon styles');
assert.ok(appStyle.includes('.card-title-row'), 'app.wxss should define icon-aware card title layout');
for (const file of ['pages/login/index.wxml', 'pages/dashboard/index.wxml', 'pages/news/index.wxml', 'pages/paper/index.wxml']) {
  assert.ok(read(file).includes('ui-icon'), `${file} should render page or section icons`);
}

const apiSource = read('services/api.js');
assert.ok(apiSource.includes('apiBaseUrlStorageKey'), 'services/api.js should support configurable backend URL');
assert.ok(apiSource.includes('formatRequestFailure'), 'services/api.js should format wx.request failures clearly');
for (const fragment of [
  '/health',
  '/market/snapshot',
  '/watchlist',
  '/news',
  '/paper/sessions',
  '/paper/summary',
  '/paper/watchlist',
  '/paper/orders',
  '/paper/positions',
  '/paper/trades',
  '/paper/cash-flows',
]) {
  assert.ok(apiSource.includes(fragment), `services/api.js should include ${fragment}`);
}
assert.ok(!apiSource.includes('/paper/admin'), 'mini program must not expose paper admin APIs');

const paperSource = read('pages/paper/index.js');
assert.ok(paperSource.includes('createPaperOrder'), 'paper page should support user trading');
assert.ok(paperSource.includes('startPolling'), 'paper page should refresh account data after backend updates');
assert.ok(!paperSource.toLowerCase().includes('admin'), 'paper page must not expose admin login');

const sessionSource = read('services/session.js');
assert.ok(sessionSource.includes('requirePaperLogin'), 'session service should expose a content gate');
assert.ok(sessionSource.includes('/pages/login/index'), 'session gate should redirect to login page');

const loginSource = read('pages/login/index.js');
assert.ok(loginSource.includes('loginPaperAccount'), 'login page should support user account login');
assert.ok(loginSource.includes('createPaperAccount'), 'login page should support user account creation');
assert.ok(loginSource.includes('goHome'), 'login success should enter dashboard tab');
assert.ok(!loginSource.toLowerCase().includes('admin'), 'login page must not expose admin login');

const dashboardSource = read('pages/dashboard/index.js');
assert.ok(dashboardSource.includes('requirePaperLogin'), 'dashboard should require login before loading content');
assert.ok(dashboardSource.includes('startPolling'), 'dashboard should poll to stay in sync with backend updates');
assert.ok(dashboardSource.includes("market: 'INDEX'"), 'dashboard should load main indices from a dedicated INDEX market query');
assert.ok(dashboardSource.includes('preferredIndexOrder'), 'dashboard should prioritize the configured main index order');

const newsSource = read('pages/news/index.js');
assert.ok(newsSource.includes('requirePaperLogin'), 'news should require login before loading content');
assert.ok(paperSource.includes('requirePaperLogin'), 'paper trading should require login before loading content');

console.log('mini program structure validation passed');
