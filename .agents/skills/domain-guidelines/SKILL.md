---
name: domain-guidelines
description: >-
  Navigates repository domain terms (Coalition, Seat, Baseline, Swing Model, etc.),
  ADR invariants (zero cost, static generation), and single-context repository rules.
---

# Domain Guidelines & Architecture Rules

This repository operates under a **single-context layout**.

---

## 1. Essential Reading

Before modifying logic or generating outputs:
1. **`CONTEXT.md`**: Canonical glossary of Malaysian electoral terms.
   - *Coalition*: PH, BN, PN, GPS, GRS. (Avoid: party, alliance, bloc unless distinguishing sub-parties).
   - *Seat*: One of the 222 parliamentary constituencies. (Avoid: district).
   - *Majority*: 112+ seats. (Avoid: win).
   - *Government Coalition*: PH + BN + GPS + GRS + minor parties. (Avoid: Unity government in code).
   - *Non-government*: All seats/coalitions outside the Government Coalition (preferred over "Opposition" which only strictly applies to PN).
   - *Baseline*: Fixed GE15 (2022) results and demographics.
   - *Projection / Seat Call*: Model output. Never use "prediction" or "forecast".
   - *Swing Model*: Mathematical model applying sentiment & state signals uniformly within states.
2. **`docs/adr/`**: Key Architecture Decision Records:
   - **ADR 0002 / ADR 0007**: Zero recurring cost by default (self-hosted local CPU inference, free data sources, no paid APIs).
   - **ADR 0006**: Static HTML generation for the public page (`public/index.html` + dated permalinks).
   - **ADR 0008 / 0009 / 0010**: Domain constraints for Postcodes, MP Profiles, and Bill Tracking.

---

## 2. Consistency Guidelines

- Use exact canonical terms in issues, variable names, documentation, and user explanations.
- Never assert per-seat bespoke predictions — every seat call is pure arithmetic against GE15 baselines.
- Maintain the decoupling between data (`data/*.json`) and logic (`src/lpa/`).
