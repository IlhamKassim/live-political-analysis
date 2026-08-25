import { beforeEach, describe, expect, it, vi } from "vitest";
import { readRecentSeats, recordRecentSeat } from "./storage";

beforeEach(() => {
  window.localStorage.clear();
});

describe("recentSeats", () => {
  it("reads back an empty list when nothing has been recorded", () => {
    expect(readRecentSeats()).toEqual([]);
  });

  it("records a Seat and reads it back", () => {
    recordRecentSeat({ code: "P.102", name: "Bangi" });
    expect(readRecentSeats()).toEqual([{ code: "P.102", name: "Bangi" }]);
  });

  it("puts the newest lookup first", () => {
    recordRecentSeat({ code: "P.101", name: "Hulu Langat" });
    recordRecentSeat({ code: "P.102", name: "Bangi" });
    expect(readRecentSeats().map((s) => s.code)).toEqual(["P.102", "P.101"]);
  });

  it("moves an already-recorded Seat to the front instead of duplicating it", () => {
    recordRecentSeat({ code: "P.101", name: "Hulu Langat" });
    recordRecentSeat({ code: "P.102", name: "Bangi" });
    recordRecentSeat({ code: "P.101", name: "Hulu Langat" });
    expect(readRecentSeats().map((s) => s.code)).toEqual(["P.101", "P.102"]);
  });

  it("caps the list at four, dropping the oldest", () => {
    for (const code of ["A", "B", "C", "D", "E"]) {
      recordRecentSeat({ code, name: code });
    }
    expect(readRecentSeats().map((s) => s.code)).toEqual(["E", "D", "C", "B"]);
  });

  it("reads back an empty list rather than throwing when storage is unusable", () => {
    const spy = vi.spyOn(window.localStorage, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    expect(readRecentSeats()).toEqual([]);
    spy.mockRestore();
  });

  it("a failed write never throws back into the caller", () => {
    const spy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });
    expect(() => recordRecentSeat({ code: "P.102", name: "Bangi" })).not.toThrow();
    spy.mockRestore();
  });

  it("ignores garbage already sitting in storage rather than crashing", () => {
    window.localStorage.setItem("pk-recent-seats", "not json");
    expect(readRecentSeats()).toEqual([]);
    window.localStorage.setItem("pk-recent-seats", JSON.stringify([{ code: 1 }]));
    expect(readRecentSeats()).toEqual([]);
  });
});
