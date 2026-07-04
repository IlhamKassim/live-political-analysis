#!/usr/bin/env python3
"""Bake the per-state economy report card from official DOSM open data (CC BY 4.0).

Endpoints (live-tested 2026-07-04; api.data.gov.my — follow redirects, ONE filter
param with comma-separated value@column pairs):
  • gdp_state_real_supply  — real GDP by state; series=growth_yoy|abs, sector=p0
                             (constant 2015 prices; latest machine-readable year 2023;
                             15 geographies — Putrajaya is folded into W.P. Kuala Lumpur)
  • population_state       — for derived REAL GDP per capita (abs RM mil / population)
  • lfs_qtr_state          — u_rate, quarterly, all 16 states (latest 2025-Q3)
  • hies_state             — income_median + gini + poverty, 2022 snapshot, all 16

Output: public/data/state-econ.json
  { "year_gdp": 2023, "national": {...}, "states": { "<state>": {
      gdp_growth, gdp_pc, u_rate, u_qtr, income_median, income_year } } }
"""
import json
import os
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "public", "data", "state-econ.json")
API = "https://api.data.gov.my/data-catalogue"


def fetch(id_, **params):
    q = {"id": id_, "limit": params.pop("limit", 1000)}
    q.update(params)
    url = API + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "MyPolitikEcon/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:   # urllib follows the 301
        return json.loads(r.read().decode())


def main():
    growth = fetch("gdp_state_real_supply", filter="growth_yoy@series,p0@sector", sort="-date,state")
    absgdp = fetch("gdp_state_real_supply", filter="abs@series,p0@sector", sort="-date,state")
    pop = fetch("population_state", filter="overall_sex@sex,overall_age@age,overall_ethnicity@ethnicity", sort="-date,state")
    lfs = fetch("lfs_qtr_state", sort="-date,state", limit=64)
    hies = fetch("hies_state", limit=32)

    latest_gdp_year = max(r["date"][:4] for r in growth)
    g_by_state = {r["state"]: r["value"] for r in growth if r["date"][:4] == latest_gdp_year}
    a_by_state = {r["state"]: r["value"] for r in absgdp if r["date"][:4] == latest_gdp_year}
    a_prev = {r["state"]: r["value"] for r in absgdp if int(r["date"][:4]) == int(latest_gdp_year) - 1}
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
    tot_prev = sum(v for s, v in a_prev.items() if s != "Supra")
    nat_growth = round(100 * (tot / tot_prev - 1), 2) if tot_prev else None
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
            "gdp_growth": nat_growth,
            "gdp_pc": int(round(tot * 1e6 / (nat_pop * 1e3))) if nat_pop else None,
            "u_rate": u_by_state.get("Malaysia") or nat_u,
        },
        "license": "DOSM via data.gov.my · CC BY 4.0",
        "states": states,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"state econ: {len(states)} states, GDP {latest_gdp_year}, LFS {u_qtr}, HIES {inc_year}")
    print(f"  national: growth {nat_growth}%, per-capita RM{out['national']['gdp_pc']}, u {out['national']['u_rate']}%")


if __name__ == "__main__":
    main()
