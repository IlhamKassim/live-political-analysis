#!/usr/bin/env bash
set -u

status=0

pass() {
  printf 'PASS %s\n' "$1"
}

fail() {
  printf 'FAIL %s\n' "$1"
  status=1
}

if node --check public/app.js >/tmp/mypolitik-node-check.log 2>&1; then
  pass "node --check public/app.js"
else
  fail "node --check public/app.js"
  cat /tmp/mypolitik-node-check.log
fi

if python3 -m py_compile pipeline/*.py >/tmp/mypolitik-py-compile.log 2>&1; then
  pass "python3 -m py_compile pipeline/*.py"
else
  fail "python3 -m py_compile pipeline/*.py"
  cat /tmp/mypolitik-py-compile.log
fi

if node <<'NODE' >/tmp/mypolitik-json-parse.log 2>&1
const fs = require("fs");
const path = require("path");

const dir = path.join("public", "data");
const files = fs.readdirSync(dir)
  .filter((name) => name.endsWith(".json"))
  .sort();

if (files.length === 0) {
  throw new Error("No JSON files found in public/data");
}

for (const file of files) {
  JSON.parse(fs.readFileSync(path.join(dir, file), "utf8"));
}
NODE
then
  pass "JSON.parse public/data/*.json"
else
  fail "JSON.parse public/data/*.json"
  cat /tmp/mypolitik-json-parse.log
fi

if node <<'NODE' >/tmp/mypolitik-ge15-tally.log 2>&1
const fs = require("fs");

const expected = {
  PH: 82,
  PN: 74,
  BN: 30,
  GPS: 23,
  GRS: 6,
  WARISAN: 3,
};
const results = JSON.parse(fs.readFileSync("public/data/results-ge15.json", "utf8"));
const tally = {};

for (const row of Object.values(results)) {
  const coalition = row.coalition;
  tally[coalition] = (tally[coalition] || 0) + 1;
}

for (const [coalition, count] of Object.entries(expected)) {
  if (tally[coalition] !== count) {
    throw new Error(`${coalition}: expected ${count}, got ${tally[coalition] || 0}`);
  }
}

const expectedTotal = 222;
const actualTotal = Object.values(tally).reduce((sum, count) => sum + count, 0);
if (actualTotal !== expectedTotal) {
  throw new Error(`total: expected ${expectedTotal}, got ${actualTotal}`);
}
NODE
then
  pass "GE15 coalition tally"
else
  fail "GE15 coalition tally"
  cat /tmp/mypolitik-ge15-tally.log
fi

if python3 pipeline/n9_results.py --check >/tmp/mypolitik-n9-check.log 2>&1; then
  pass "n9_results.py --check (official N9 2026 layers in sync)"
else
  fail "n9_results.py --check"
  cat /tmp/mypolitik-n9-check.log
fi

if node <<'NODE' >/tmp/mypolitik-politicians.log 2>&1
const fs = require("fs");
const p = "public/data/politicians.json";
if (!fs.existsSync(p)) process.exit(0);   // optional dataset
const { mps } = JSON.parse(fs.readFileSync(p, "utf8"));
const codes = Object.keys(mps);
if (codes.length !== 222) throw new Error(`expected 222 MPs, got ${codes.length}`);
for (const [code, m] of Object.entries(mps)) {
  if (!m.name) throw new Error(`${code}: no name`);
  if (m.photo) {
    if (!fs.existsSync("public/" + m.photo)) throw new Error(`${code}: photo file missing ${m.photo}`);
    if (!m.photo_credit) throw new Error(`${code}: photo without credit`);
  }
}
NODE
then
  pass "politicians roster (222 MPs, photos have files + credit)"
else
  fail "politicians roster"
  cat /tmp/mypolitik-politicians.log
fi

exit "$status"
