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

  it("is not-in-index for a postcode the pilot doesn't cover, never a guess", () => {
    expect(resolveQuery("50000", INDEX)).toEqual({ kind: "notFound", reason: "not-in-index" });
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
