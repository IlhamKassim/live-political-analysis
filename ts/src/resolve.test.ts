import { describe, expect, it } from "vitest";
import { resolveQuery } from "./resolve";
import type { ClientLookupIndex } from "./types";

// Bangi/Hulu Langat/Cheras — the same real pilot slice
// data/postcode_seat_index.json ships (ADR 0008), so these tests exercise
// the actual shape the client will see, not an invented one.
const INDEX: ClientLookupIndex = {
  seats: {
    "P.101": { code: "P.101", name: "Hulu Langat", state: "Selangor", hasProfile: false, mpName: null },
    "P.102": {
      code: "P.102",
      name: "Bangi",
      state: "Selangor",
      hasProfile: true,
      mpName: "Syahredzan Johan",
    },
  },
  postcodes: {
    "43000": ["P.102"],
    "43100": ["P.101"],
    "43200": ["P.101", "P.102"],
  },
  postcodeCatalogue: {
    "43000": [{ city: "Kajang", state: "Selangor" }],
    "50000": [{ city: "Kuala Lumpur", state: "W.P. Kuala Lumpur" }],
  },
};

describe("resolveQuery", () => {
  it("resolves a postcode that names exactly one Seat", () => {
    const result = resolveQuery("43000", INDEX);
    expect(result).toEqual({ kind: "resolved", seat: INDEX.seats["P.102"] });
  });

  it("is ambiguous for a postcode that straddles Seats, listing every candidate", () => {
    const result = resolveQuery("43200", INDEX);
    expect(result.kind).toBe("ambiguous");
    if (result.kind === "ambiguous") {
      expect(result.candidates.map((s) => s.code)).toEqual(["P.101", "P.102"]);
    }
  });

  it("is unresolved for a valid official postcode with no verified Seat mapping", () => {
    expect(resolveQuery("50000", INDEX)).toEqual({
      kind: "unresolved",
      postcode: "50000",
      localities: [{ city: "Kuala Lumpur", state: "W.P. Kuala Lumpur" }],
      candidates: [],
    });
  });

  it("resolves candidate Seats for an unmapped postcode when estimates are available", () => {
    const withEstimates = { ...INDEX, postcodeEstimates: { "50000": ["P.102"] } };
    expect(resolveQuery("50000", withEstimates)).toEqual({
      kind: "unresolved",
      postcode: "50000",
      localities: [{ city: "Kuala Lumpur", state: "W.P. Kuala Lumpur" }],
      candidates: [INDEX.seats["P.102"]],
    });
  });

  it("is invalid for a five-digit code absent from the official catalogue and mappings", () => {
    expect(resolveQuery("99999", INDEX)).toEqual({ kind: "notFound", reason: "invalid-postcode" });
  });

  it("preserves a verified legacy mapping even when the official catalogue omits it", () => {
    const legacy = { ...INDEX, postcodes: { ...INDEX.postcodes, "43701": ["P.101"] } };
    expect(resolveQuery("43701", legacy)).toEqual({ kind: "resolved", seat: INDEX.seats["P.101"] });
  });

  it("matches a Seat name case-insensitively", () => {
    expect(resolveQuery("bangi", INDEX)).toEqual({ kind: "resolved", seat: INDEX.seats["P.102"] });
    expect(resolveQuery("BANGI", INDEX)).toEqual({ kind: "resolved", seat: INDEX.seats["P.102"] });
  });

  it("matches a Seat name by substring", () => {
    expect(resolveQuery("hulu", INDEX)).toEqual({ kind: "resolved", seat: INDEX.seats["P.101"] });
  });

  it("trims surrounding whitespace before matching", () => {
    expect(resolveQuery("  43000  ", INDEX)).toEqual({ kind: "resolved", seat: INDEX.seats["P.102"] });
  });

  it("is not-in-index for an empty query rather than matching everything", () => {
    expect(resolveQuery("", INDEX)).toEqual({ kind: "notFound", reason: "not-in-index" });
    expect(resolveQuery("   ", INDEX)).toEqual({ kind: "notFound", reason: "not-in-index" });
  });

  it("is not-in-index for a name with no substring match", () => {
    expect(resolveQuery("nowhere", INDEX)).toEqual({ kind: "notFound", reason: "not-in-index" });
  });
});
