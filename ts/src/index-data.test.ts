import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { _resetClientIndexCache, loadClientIndex } from "./index-data";

const REAL = { seats: { "P.102": { code: "P.102" } }, postcodes: { "43000": ["P.102"] } };

beforeEach(() => {
  _resetClientIndexCache();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loadClientIndex", () => {
  it("returns the parsed index on a successful fetch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(REAL) }),
    );
    await expect(loadClientIndex()).resolves.toEqual(REAL);
  });

  it("caches the promise — a second call does not fetch again", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(REAL) });
    vi.stubGlobal("fetch", fetchMock);
    await loadClientIndex();
    await loadClientIndex();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rejects on a non-ok response rather than caching a broken result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    await expect(loadClientIndex()).rejects.toThrow(/404/);
  });

  it("rejects a payload missing seats/postcodes instead of returning it silently", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ nope: true }) }),
    );
    await expect(loadClientIndex()).rejects.toThrow(/not a valid client lookup index/);
  });
});
