# Postcode → Seat point-estimate spike

**Status:** offline audit completed; public fallback stopped

**Checked:** 10 September 2026

**Scope:** generated estimate and quality-report artifacts only; no live lookup
or UI changes

## Decision

Do not use the GeoNames point estimates in the public postcode lookup.

The source and processing are reproducible, but the result disagrees too often
with existing verified postcode-to-Seat mappings. A valid postcode without a
verified mapping must remain unresolved.

## Sources and method

### GeoNames postcode points

- Download: `https://download.geonames.org/export/zip/MY.zip`
- Website and required attribution: `https://www.geonames.org/`
- Licence: Creative Commons Attribution 4.0
- Input size: 2,757 unique postcodes and 2,812 distinct coordinate records
- Coordinate reference system: WGS84 longitude/latitude
- Important limit: GeoNames calls latitude and longitude **estimated**. Its
  readme says unmatched places may use the average of neighbouring postcodes.

Every distinct coordinate record is preserved. Exact duplicate records for the
same postcode are removed. A postcode's candidate set is the union of all Seats
that contain or touch any of its points. A point on a shared boundary matches
every touching Seat.

These are representative points, not postcode polygons. They cannot show all
Seats crossed by a postcode.

### Parliamentary Seat boundaries

- Dataset:
  `https://raw.githubusercontent.com/dosm-malaysia/data-open/main/datasets/geodata/electoral_0_parlimen.geojson`
- Publisher repository: Department of Statistics Malaysia (DOSM),
  `https://github.com/dosm-malaysia/data-open`
- Geometry: 222 unsimplified parliamentary Seat MultiPolygons
- Coordinate reference system: explicitly declared as
  `urn:ogc:def:crs:OGC:1.3:CRS84` (longitude/latitude)
- Processing: Python standard-library ray casting against the source polygons;
  no display projection or simplification

The file's metadata still does not state its delimitation vintage. Its 222
current Seat codes and pre-GE15 repository history are not enough to label it
as a specific SPR release.

## Audit result

The full report is `data/postcode_seat_estimate_quality.json`. It compares the
point result with every existing verified mapping in
`data/postcode_seat_index.json`.

| Measure | Result |
| --- | ---: |
| Verified postcodes checked | 339 |
| Verified Seat references | 352 |
| Verified-Seat recall | 56.8% |
| Exact-set agreement | 56.6% (192/339) |
| Unresolved verified postcodes | 11.8% (40/339) |
| Recall failures | 143 |
| Mean resolved candidate-set size | 1.03 |
| Median / 95th percentile / maximum | 1 / 1 / 2 |

The low recall is not caused by broad candidate lists. Almost every resolved
point produces one Seat, but that Seat is often different from the verified
mapping. State-level recall is 33.3% in Kedah, 37.9% in Pulau Pinang, 44.4% in
Johor, and 45.2% in Perak. This is broad and systematic enough to stop public
integration.

The point for postcode `89607` is `(115.9625, 5.6064)`. It falls in `P.176` in
the DOSM file. This remains an offline estimate only.

## Artifacts and reproduction

- `src/lpa/postcode_seat_estimates.py`: parsing, geometry, output, and quality
  calculations
- `scripts/refresh_postcode_seat_estimates.py`: explicit maintainer-run refresh
- `data/postcode_seat_estimates.json`: separate estimated candidate sets with
  source, licence, attribution, and limitation metadata
- `data/postcode_seat_estimate_quality.json`: aggregate, state-level, and
  per-failure audit details

Run:

```bash
PYTHONPATH=src .venv/bin/python scripts/refresh_postcode_seat_estimates.py
```

The script downloads both static public inputs when local paths are not given.
For a repeatable review with already-downloaded files, pass `--geonames MY.zip`
and `--boundaries electoral_0_parlimen.geojson`. The output is byte-stable for
the same inputs. Pass `--generated-at YYYY-MM-DD` only when a dated refresh
record is needed.

## Public-resolution rule

The verified mapping remains authoritative and always wins. The generated
estimate file is not included in `public/data/lookup-index.json`, and the
TypeScript resolver does not read it. A postcode present only in the official
data.gov.my catalogue is still shown as valid but without a verified Seat
mapping.

Reconsidering this needs a better postcode geography source, preferably
postcode polygons, and confirmation of the Seat-boundary vintage. It also
needs a new human-approved quality threshold before any UI work resumes.