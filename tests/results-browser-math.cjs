// Exercise the interpolation used by the browser; no solver or run files are modified.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../scripts/results_browser.html'), 'utf8');
const helpers = html.slice(html.indexOf('function bracket('), html.indexOf('function plot(canvas'));
const context = vm.createContext({});
vm.runInContext(helpers, context);
const interpolate = context.interpolate;
const rows = [[0, 10], [20, 30]], logs = [2, 4], angles = [-90, 90];
assert.equal(interpolate(rows, logs, angles, 3, 0), 15);
assert.equal(interpolate(rows, logs, angles, 2, -90), 0);
assert.equal(interpolate(rows, logs, angles, 4, 90), 30);
assert.equal(interpolate([[0, 10]], [3], angles, 3, 0), 5);
assert.equal(interpolate(rows, logs, angles, 1, -100), 0);
console.log('Browser interpolation checks passed');
