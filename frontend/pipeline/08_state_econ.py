#!/usr/bin/env python3
"""Bake the per-state economy report card from official DOSM open data (CC BY 4.0).

Endpoints (live-tested 2026-07-04; api.data.gov.my — follow redirects, ONE filter
param with comma-separated value@column pairs):
  • DOSM GDP by State 2025 workbook — real GDP by state (constant 2015 prices),
                             including W.P. Putrajaya; this official release is newer
                             than the lagging machine-readable API series
  • population_state       — for derived REAL GDP per capita (abs RM mil / population)
  • lfs_qtr_state          — u_rate, quarterly, all 16 states (latest 2025-Q3)
  • hies_state             — income_median + gini + poverty, latest available release

Output: public/data/state-econ.json
  { "year_gdp": 2025, "national": {...}, "states": { "<state>": {
      gdp_growth, gdp_pc, u_rate, u_qtr, income_median, income_year } } }
"""
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "public", "data", "state-econ.json")
API = "https://api.data.gov.my/data-catalogue"
GDP_2025_WORKBOOK = "https://www.dosm.gov.my/portal-main/release-document-log?release_document_id=19977"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def fetch(id_, **params):
    q = {"id": id_, "limit": params.pop("limit", 1000)}
    q.update(params)
    url = API + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "MyPolitikEcon/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:   # urllib follows the 301
        return json.loads(r.read().decode())


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MyPolitikEcon/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def official_gdp_2025():
    """Read DOSM workbook table A7/A8 without adding an XLSX dependency."""
    with zipfile.ZipFile(BytesIO(fetch_bytes(GDP_2025_WORKBOOK))) as book:
        strings = ["".join(x.itertext()) for x in ET.fromstring(book.read("xl/sharedStrings.xml")).findall(NS + "si")]
        root = ET.fromstring(book.read("xl/worksheets/sheet7.xml"))

    rows = {}
    for row in root.find(NS + "sheetData"):
        cells = {}
        for cell in row.findall(NS + "c"):
            value = cell.find(NS + "v")
            if value is None:
                continue
            col = "".join(ch for ch in cell.attrib["r"] if ch.isalpha())
            cells[col] = strings[int(value.text)] if cell.attrib.get("t") == "s" else value.text
        rows[int(row.attrib["r"])] = cells

    amounts, previous, growth = {}, {}, {}
    for i in range(5, 21):
        state = rows[i].get("B")
        if state:
            amounts[state] = float(rows[i]["E"])
            previous[state] = float(rows[i]["D"])
    for i in range(28, 44):
        state = rows[i].get("B")
        if state:
            growth[state] = float(rows[i]["E"])
    assert len(amounts) == len(growth) == 16, "unexpected GDP-by-state workbook layout"
    return growth, amounts, previous, 5.151


def main():
    try:
        g_by_state, a_by_state, a_prev, nat_growth = official_gdp_2025()
        latest_gdp_year = "2025"
    except Exception as e:
        # The open-data feed remains a conservative fallback if DOSM moves the release
        # document; retain its dynamic latest-year behaviour rather than failing stale.
        print(f"official GDP workbook unavailable ({e}); falling back to data.gov.my")
        growth = fetch("gdp_state_real_supply", filter="growth_yoy@series,p0@sector", sort="-date,state")
        absgdp = fetch("gdp_state_real_supply", filter="abs@series,p0@sector", sort="-date,state")
        latest_gdp_year = max(r["date"][:4] for r in growth)
        g_by_state = {r["state"]: r["value"] for r in growth if r["date"][:4] == latest_gdp_year}
        a_by_state = {r["state"]: r["value"] for r in absgdp if r["date"][:4] == latest_gdp_year}
        a_prev = {r["state"]: r["value"] for r in absgdp if int(r["date"][:4]) == int(latest_gdp_year) - 1}
        tot_now = sum(v for s, v in a_by_state.items() if s != "Supra")
        tot_prev = sum(v for s, v in a_prev.items() if s != "Supra")
        nat_growth = 100 * (tot_now / tot_prev - 1) if tot_prev else None
    pop = fetch("population_state", filter="overall_sex@sex,overall_age@age,overall_ethnicity@ethnicity", sort="-date,state")
    lfs = fetch("lfs_qtr_state", sort="-date,state", limit=64)
    hies = fetch("hies_state", limit=32)

    pop_years = sorted({r["date"][:4] for r in pop})
    pop_year = latest_gdp_year if latest_gdp_year in pop_years else pop_years[-1]
    p_by_state = {r["state"]: r["population"] for r in pop if r["date"][:4] == pop_year}

    latest_q = max(r["date"] for r in lfs)
    u_by_state = {r["state"]: r["u_rate"] for r in lfs if r["date"] == latest_q}
    qnum = (int(latest_q[5:7]) - 1) // 3 + 1
    u_qtr = f"{latest_q[:4]}-Q{qnum}"
    # national unemployment: no Malaysia row in the state file — derive from the sums
    lf_tot = sum(r["lf"] for r in lfs if r["date"] == latest_q)
    lf_un = sum(r["lf_unemployed"] for r in lfs if r["date"] == latest_q)
    nat_u = round(100 * lf_un / lf_tot, 1) if lf_tot else None

    inc_year = max(r["date"][:4] for r in hies)
    inc_by_state = {r["state"]: r["income_median"] for r in hies if r["date"][:4] == inc_year}

    # national aggregates (GDP has no Malaysia row): growth from summed abs;
    # per-capita from summed abs over summed population (excluding the 'Supra' row)
    tot = sum(v for s, v in a_by_state.items() if s != "Supra")
    nat_pop = sum(v for s, v in p_by_state.items() if s in a_by_state)

    states = {}
    for st, g in g_by_state.items():
        if st == "Supra":
            continue
        entry = {"gdp_growth": round(g, 1)}
        if st in a_by_state and st in p_by_state and p_by_state[st]:
            entry["gdp_pc"] = int(round(a_by_state[st] * 1e6 / (p_by_state[st] * 1e3)))
        if st in u_by_state:
            entry["u_rate"] = u_by_state[st]
        if st in inc_by_state:
            entry["income_median"] = int(inc_by_state[st])
        states[st] = entry
    # LFS/HIES-only geographies (e.g. W.P. Putrajaya — GDP folded into KL)
    for st in u_by_state:
        if st not in states and st != "Malaysia":
            states[st] = {"u_rate": u_by_state[st]}
            if st in inc_by_state:
                states[st]["income_median"] = int(inc_by_state[st])

    assert len([s for s in states if not s.startswith("W.P.")]) >= 13, "missing states"
    out = {
        "year_gdp": int(latest_gdp_year), "u_qtr": u_qtr, "income_year": int(inc_year),
        "national": {
            "gdp_growth": round(nat_growth, 1) if nat_growth is not None else None,
            "gdp_pc": int(round(tot * 1e6 / (nat_pop * 1e3))) if nat_pop else None,
            "u_rate": u_by_state.get("Malaysia") or nat_u,
        },
        "license": "DOSM: GDP by State 2025; HIES 2024; Labour Force Survey via data.gov.my · CC BY 4.0",
        "sources": {
            "gdp": "https://www.dosm.gov.my/portal-main/release-content/gross-domestic-product-gdp-by-state-2025",
            "income": "https://v2.dosm.gov.my/portal-main/release-content/household-income-survey-report--malaysia--states-2024",
            "labour": "https://api.data.gov.my/data-catalogue?id=lfs_qtr_state",
        },
        "states": states,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"state econ: {len(states)} states, GDP {latest_gdp_year}, LFS {u_qtr}, HIES {inc_year}")
    print(f"  national: growth {nat_growth}%, per-capita RM{out['national']['gdp_pc']}, u {out['national']['u_rate']}%")


if __name__ == "__main__":
    main()
