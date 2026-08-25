import { describe, expect, it } from "vitest";
import { initialModel, transition } from "./state-machine";
import type { ResolutionResult } from "./types";

const RESOLVED: ResolutionResult = {
  kind: "resolved",
  seat: { code: "P.102", name: "Bangi", state: "Selangor", hasProfile: true, mpName: "x" },
};
const AMBIGUOUS: ResolutionResult = { kind: "ambiguous", candidates: [] };
const NOT_FOUND: ResolutionResult = { kind: "notFound", reason: "not-in-index" };

describe("transition", () => {
  it("starts idle", () => {
    expect(initialModel.state).toBe("idle");
  });

  it("submitQuery moves to searching and remembers the query", () => {
    const model = transition(initialModel, { type: "submitQuery", query: "43000" });
    expect(model).toEqual({ state: "searching", query: "43000", result: null });
  });

  it("requestLocation moves to locating without touching the query", () => {
    const withQuery = transition(initialModel, { type: "submitQuery", query: "kept" });
    const model = transition(withQuery, { type: "requestLocation" });
    expect(model.state).toBe("locating");
    expect(model.query).toBe("kept");
  });

  it("resolved with a resolved result lands on the resolved state", () => {
    const model = transition(initialModel, { type: "resolved", result: RESOLVED });
    expect(model.state).toBe("resolved");
    expect(model.result).toBe(RESOLVED);
  });

  it("resolved with an ambiguous result lands on the ambiguous state", () => {
    const model = transition(initialModel, { type: "resolved", result: AMBIGUOUS });
    expect(model.state).toBe("ambiguous");
  });

  it("resolved with a notFound result lands on the notFound state", () => {
    const model = transition(initialModel, { type: "resolved", result: NOT_FOUND });
    expect(model.state).toBe("notFound");
  });

  it("reset always returns to the initial model, from any state", () => {
    const busy = transition(initialModel, { type: "resolved", result: RESOLVED });
    expect(transition(busy, { type: "reset" })).toEqual(initialModel);
  });

  it("never mutates the model it was given", () => {
    const before = { ...initialModel };
    transition(initialModel, { type: "submitQuery", query: "x" });
    expect(initialModel).toEqual(before);
  });
});
