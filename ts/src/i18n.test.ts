import { afterEach, describe, expect, it } from "vitest";
import { copyFor, currentLanguage } from "./i18n";

afterEach(() => {
  document.documentElement.lang = "en";
});

describe("currentLanguage", () => {
  it("reads the language the server already stamped on <html>", () => {
    document.documentElement.lang = "ms";
    expect(currentLanguage()).toBe("ms");
  });

  it("falls back to English for any other value, including none", () => {
    document.documentElement.removeAttribute("lang");
    expect(currentLanguage()).toBe("en");
    document.documentElement.lang = "en-GB";
    expect(currentLanguage()).toBe("en");
  });
});

describe("copyFor", () => {
  it("translates the two loading states the design handoff left undrawn in BM", () => {
    expect(copyFor("ms").searching).toBe("Membaca indeks sempadan dalam pelayar anda");
    expect(copyFor("ms").locating).toBe("Membaca lokasi dalam pelayar anda");
  });

  it("leaves no string untranslated — every BM string differs from its English pair", () => {
    const en = copyFor("en");
    const ms = copyFor("ms");
    const flatten = (copy: ReturnType<typeof copyFor>): string[] => [
      copy.searching,
      copy.locating,
      copy.ambiguousHeading,
      copy.boundariesFootnote,
      copy.noProfileYet,
      copy.noMatchTag,
      ...Object.values(copy.noMatch),
      ...Object.values(copy.routes),
      copy.seeYourMp("Bangi"),
      copy.resolvedNoProfile("Bangi", "Selangor"),
    ];
    const enStrings = flatten(en);
    const msStrings = flatten(ms);
    expect(msStrings).toHaveLength(enStrings.length);
    for (const [i, english] of enStrings.entries()) {
      expect(msStrings[i]).not.toBe(english);
    }
  });
});
