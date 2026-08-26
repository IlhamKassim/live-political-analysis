import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { _resetClientIndexCache } from "./index-data";
import { mountLookup } from "./dom";

const INDEX = {
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
  postcodes: { "43000": ["P.102"], "43100": ["P.101"], "43200": ["P.101", "P.102"], "99999": [] },
};

function buildContainer(): HTMLElement {
  const container = document.createElement("div");
  container.innerHTML = `
    <form data-pk-lookup-form>
      <input data-pk-lookup-input>
      <button type="submit">Search</button>
    </form>
    <button type="button" data-pk-locate>Use my location</button>
    <div data-pk-lookup-results hidden></div>
  `;
  document.body.append(container);
  return container;
}

function flushMicrotasks(): Promise<void> {
  // The submit handler's chain (fetch -> .then(json) -> .then(assert) ->
  // .then(resolve)) is several microtask hops deep — a `setTimeout` macrotask
  // reliably drains all of them first, unlike a fixed count of
  // `Promise.resolve()` awaits, which under- or over-counts depending on
  // exactly how many `.then`s a given path chains through.
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function submit(container: HTMLElement, query: string): Promise<void> {
  const input = container.querySelector<HTMLInputElement>("[data-pk-lookup-input]")!;
  input.value = query;
  container.querySelector<HTMLFormElement>("[data-pk-lookup-form]")!.requestSubmit();
  await flushMicrotasks();
}

beforeEach(() => {
  _resetClientIndexCache();
  document.body.innerHTML = "";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(INDEX) }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  // A BM test would otherwise leak its `lang` into every test after it.
  document.documentElement.lang = "en";
  Object.defineProperty(navigator, "geolocation", {
    value: originalGeolocation,
    configurable: true,
  });
});

const originalGeolocation = navigator.geolocation;

/** Denies the permission, then clicks "Use my location" and settles. */
async function locateDenied(container: HTMLElement): Promise<void> {
  Object.defineProperty(navigator, "geolocation", {
    value: {
      getCurrentPosition: (_success: PositionCallback, error?: PositionErrorCallback) => {
        error?.({ code: 1, PERMISSION_DENIED: 1 } as GeolocationPositionError);
      },
    },
    configurable: true,
  });
  container.querySelector<HTMLButtonElement>("[data-pk-locate]")!.click();
  await flushMicrotasks();
}

describe("mountLookup", () => {
  it("links a resolved Seat with a profile straight to its MP profile page", async () => {
    const container = buildContainer();
    mountLookup(container);
    await submit(container, "43000");
    const link = container.querySelector<HTMLAnchorElement>(".pk-lookup-resolved-link");
    expect(link?.getAttribute("href")).toBe("/mp/P.102.html");
  });

  it("degrades a resolved Seat with no profile to an honest message, not a link", async () => {
    const container = buildContainer();
    mountLookup(container);
    await submit(container, "43100");
    expect(container.querySelector(".pk-lookup-resolved-link")).toBeNull();
    expect(container.querySelector(".pk-lookup-resolved-no-profile")?.textContent).toBe(
      "Hulu Langat, Selangor — MP profile for this Seat isn't built yet.",
    );
  });

  it("flags the input with the error class only for a not-in-index no-match", async () => {
    const container = buildContainer();
    mountLookup(container);
    const input = container.querySelector<HTMLInputElement>("[data-pk-lookup-input]")!;

    await submit(container, "99999");
    expect(input.classList.contains("pk-lookup-input-error")).toBe(true);

    await submit(container, "43000");
    expect(input.classList.contains("pk-lookup-input-error")).toBe(false);
  });

  it("the no-match state links to all four routes named in the design, including corrections", async () => {
    const container = buildContainer();
    mountLookup(container);
    await submit(container, "99999");
    const links = [...container.querySelectorAll<HTMLAnchorElement>(".pk-lookup-routes a")];
    const labels = links.map((a) => a.textContent);
    expect(labels).toEqual([
      "Search by name",
      "Browse all 222 Seats",
      "Check registration with SPR",
      "Report a mistake in this index",
    ]);
    const browseLink = links.find((a) => a.textContent === "Browse all 222 Seats");
    expect(browseLink?.getAttribute("href")).toBe("/projection/");
  });

  it("browse all seats links to /projection/ms/ when in BM", async () => {
    document.documentElement.lang = "ms";
    const container = buildContainer();
    mountLookup(container);
    await submit(container, "99999");
    const links = [...container.querySelectorAll<HTMLAnchorElement>(".pk-lookup-routes a")];
    const browseLink = links.find((a) => a.textContent === "Lihat semua 222 Kerusi");
    expect(browseLink?.getAttribute("href")).toBe("/projection/ms/");
  });

  it("clicking \"Search by name\" clears the input, focuses it, and returns to idle", async () => {
    const container = buildContainer();
    mountLookup(container);
    await submit(container, "99999");
    const input = container.querySelector<HTMLInputElement>("[data-pk-lookup-input]")!;
    const searchByName = [...container.querySelectorAll<HTMLAnchorElement>(".pk-lookup-routes a")].find(
      (a) => a.textContent === "Search by name",
    )!;
    searchByName.click();
    expect(input.value).toBe("");
    expect(document.activeElement).toBe(input);
    expect(container.querySelector<HTMLElement>("[data-pk-lookup-results]")!.hidden).toBe(true);
  });

  it("a denied location offers the two routes that aren't about the postcode index", async () => {
    const container = buildContainer();
    mountLookup(container);
    await locateDenied(container);
    expect(container.querySelector(".pk-lookup-no-match-reason")?.textContent).toBe(
      "Location permission was declined.",
    );
    const labels = [...container.querySelectorAll(".pk-lookup-routes a")].map((a) => a.textContent);
    expect(labels).toEqual(["Search by name", "Browse all 222 Seats"]);
  });

  it("a denied location never flags the input, which holds no mistaken query", async () => {
    const container = buildContainer();
    mountLookup(container);
    await locateDenied(container);
    const input = container.querySelector<HTMLInputElement>("[data-pk-lookup-input]")!;
    expect(input.classList.contains("pk-lookup-input-error")).toBe(false);
  });

  it("\"Search by name\" from a denied location returns focus to the still-live field", async () => {
    const container = buildContainer();
    mountLookup(container);
    await locateDenied(container);
    const input = container.querySelector<HTMLInputElement>("[data-pk-lookup-input]")!;
    container.querySelector<HTMLAnchorElement>(".pk-lookup-routes a")!.click();
    expect(document.activeElement).toBe(input);
    expect(container.querySelector<HTMLElement>("[data-pk-lookup-results]")!.hidden).toBe(true);
  });

  it("renders BM copy when the page is in BM, for every state that has any", async () => {
    document.documentElement.lang = "ms";
    const container = buildContainer();
    mountLookup(container);

    await submit(container, "43200");
    expect(container.querySelector(".pk-lookup-ambiguous-heading")?.textContent).toBe(
      "Lebih daripada satu Kerusi sepadan — pilih Kerusi anda:",
    );
    expect(container.querySelector(".pk-lookup-candidate-mp")?.textContent).toBe(
      "Profil Ahli Parlimen belum tersedia",
    );

    await submit(container, "99999");
    expect(container.querySelector(".pk-lookup-no-match-tag")?.textContent).toBe("TIADA PADANAN");
    expect(container.querySelector(".pk-lookup-no-match-reason")?.textContent).toBe(
      "Tiada dalam indeks poskod Suruhanjaya Pilihan Raya.",
    );

    await submit(container, "43100");
    expect(container.querySelector(".pk-lookup-resolved-no-profile")?.textContent).toBe(
      "Hulu Langat, Selangor — profil Ahli Parlimen bagi Kerusi ini belum dibina.",
    );
  });

  it("draws different copy per language for the same state", async () => {
    const container = buildContainer();
    mountLookup(container);
    await submit(container, "43200");
    const english = container.querySelector(".pk-lookup-ambiguous-heading")?.textContent;

    document.documentElement.lang = "ms";
    const malay = buildContainer();
    mountLookup(malay);
    await submit(malay, "43200");

    expect(malay.querySelector(".pk-lookup-ambiguous-heading")?.textContent).not.toBe(english);
  });

  it("an ambiguous result lists every candidate, degrading the one with no profile", async () => {
    const container = buildContainer();
    mountLookup(container);
    await submit(container, "43200");
    const rows = container.querySelectorAll(".pk-lookup-candidate");
    expect(rows).toHaveLength(2);
    expect(rows[0]?.querySelector(".pk-lookup-candidate-mp")?.textContent).toBe(
      "MP profile not yet available",
    );
    expect(rows[1]?.querySelector(".pk-lookup-candidate-mp")?.textContent).toBe("Syahredzan Johan");
  });

  it("transitions to notFound with index-unavailable copy when index fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    const container = buildContainer();
    mountLookup(container);

    await submit(container, "43000");
    expect(container.querySelector(".pk-lookup-no-match-tag")?.textContent).toBe("NO MATCH");
    expect(container.querySelector(".pk-lookup-no-match-reason")?.textContent).toBe(
      "The constituency index couldn't be loaded right now — check your connection or browse all seats below.",
    );
    const input = container.querySelector<HTMLInputElement>("[data-pk-lookup-input]")!;
    expect(input.classList.contains("pk-lookup-input-error")).toBe(false);

    const labels = [...container.querySelectorAll(".pk-lookup-routes a")].map((a) => a.textContent);
    expect(labels).toEqual(["Browse all 222 Seats"]);
  });

  it("renders BM copy when index fetch fails on a BM page", async () => {
    document.documentElement.lang = "ms";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    const container = buildContainer();
    mountLookup(container);

    await submit(container, "43000");
    expect(container.querySelector(".pk-lookup-no-match-tag")?.textContent).toBe("TIADA PADANAN");
    expect(container.querySelector(".pk-lookup-no-match-reason")?.textContent).toBe(
      "Indeks kawasan pilihan raya tidak dapat dimuatkan — semak sambungan anda atau lihat semua kerusi di bawah.",
    );
  });

  it("mount-time index fetch failure does not throw unhandled rejection and mounts cleanly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Network error")));
    const container = buildContainer();
    mountLookup(container);
    await flushMicrotasks();
    expect(container.querySelector<HTMLElement>("[data-pk-lookup-results]")!.hidden).toBe(true);
  });
});
