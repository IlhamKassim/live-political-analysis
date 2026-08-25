import { afterEach, describe, expect, it, vi } from "vitest";
import { isGeolocationSupported, locate } from "./geolocation";

const originalGeolocation = navigator.geolocation;

afterEach(() => {
  Object.defineProperty(navigator, "geolocation", {
    value: originalGeolocation,
    configurable: true,
  });
});

describe("isGeolocationSupported", () => {
  it("is false when the browser has no geolocation API", () => {
    Object.defineProperty(navigator, "geolocation", { value: undefined, configurable: true });
    expect(isGeolocationSupported()).toBe(false);
  });
});

describe("locate", () => {
  it("resolves geolocation-unsupported without ever touching the API when absent", async () => {
    Object.defineProperty(navigator, "geolocation", { value: undefined, configurable: true });
    await expect(locate()).resolves.toEqual({ kind: "notFound", reason: "geolocation-unsupported" });
  });

  it("reads a real fix but never inspects or forwards the coordinates — the privacy promise", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      // A coordinate is provided, proving the API path was exercised for
      // real — the assertion below is that `locate()`'s result carries
      // nothing about it, not that the coordinate was withheld.
      success({
        coords: { latitude: 2.9, longitude: 101.7 } as GeolocationCoordinates,
        timestamp: Date.now(),
      } as GeolocationPosition);
    });
    Object.defineProperty(navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
    });
    const result = await locate();
    expect(result).toEqual({ kind: "notFound", reason: "geolocation-unresolvable" });
    expect(JSON.stringify(result)).not.toMatch(/2\.9|101\.7/);
  });

  it("maps a permission-denied error to its own reason", async () => {
    const getCurrentPosition = vi.fn(
      (_success: PositionCallback, error?: PositionErrorCallback) => {
        error?.({ code: 1, PERMISSION_DENIED: 1 } as GeolocationPositionError);
      },
    );
    Object.defineProperty(navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
    });
    await expect(locate()).resolves.toEqual({ kind: "notFound", reason: "geolocation-denied" });
  });

  it("maps any other geolocation error to the unresolvable reason", async () => {
    const getCurrentPosition = vi.fn(
      (_success: PositionCallback, error?: PositionErrorCallback) => {
        error?.({ code: 2, PERMISSION_DENIED: 1 } as GeolocationPositionError);
      },
    );
    Object.defineProperty(navigator, "geolocation", {
      value: { getCurrentPosition },
      configurable: true,
    });
    await expect(locate()).resolves.toEqual({ kind: "notFound", reason: "geolocation-unresolvable" });
  });
});
