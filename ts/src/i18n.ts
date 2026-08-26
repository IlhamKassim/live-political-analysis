// The lookup's own EN/BM copy table (#82), client-side and self-contained.
//
// Every other PolitikKu page is rendered server-side per language by
// `politikku_shell.py`'s `t(language, en, ms)`, so its BM copy lives in
// Python. This module renders the one thing those pages do not pre-render
// — the dynamic results area — so it has to carry its own strings. They are
// not fetched from Python at runtime: there is no per-language JSON to
// fetch, and adding one would put a network read in front of a results area
// that is otherwise entirely offline once the index is cached.
//
// The language is not new plumbing either: `politikku_shell.py` already
// stamps `<html lang="en">`/`<html lang="ms">` (its `lang_attr`), so this
// module reads the language the server already decided rather than
// negotiating one of its own.
//
// Register: the BM below follows #81's settled vocabulary rather than
// retranslating from scratch — "Kerusi" for Seat, "Suruhanjaya Pilihan
// Raya" for the Election Commission, "Ahli Parlimen" for MP, and the
// homepage's own "Lokasi dibaca dalam pelayar anda" phrasing for the
// in-browser reads. Strings with no settled source (the loading, ambiguous
// and no-match states are exactly the three the design handoff lists as
// "still undrawn" in BM) are new copy and want a native-BM check, the same
// caveat #81 shipped under.

import type { NoMatchReason } from "./types";

export type Language = "en" | "ms";

/** The language the server already chose, read off `<html lang>`. */
export function currentLanguage(): Language {
  return document.documentElement.lang === "ms" ? "ms" : "en";
}

export interface RouteCopy {
  readonly searchByName: string;
  readonly browseAllSeats: string;
  readonly checkRegistration: string;
  readonly reportMistake: string;
}

/** Keyed off `NoMatchReason` itself, so a fifth reason fails to compile
 * here — at the table that is actually missing a string — rather than at
 * `dom.ts`'s lookup of it. */
export type NoMatchCopy = Readonly<Record<NoMatchReason, string>>;

export interface LookupCopy {
  readonly searching: string;
  readonly locating: string;
  readonly ambiguousHeading: string;
  readonly boundariesFootnote: string;
  readonly noProfileYet: string;
  readonly noMatchTag: string;
  readonly noMatch: NoMatchCopy;
  readonly routes: RouteCopy;
  /** `${seat.name} — see your MP →` */
  readonly seeYourMp: (seatName: string) => string;
  /** `${seat.name}, ${seat.state} — MP profile ... isn't built yet.` */
  readonly resolvedNoProfile: (seatName: string, state: string) => string;
}

const EN: LookupCopy = {
  searching: "Reading the boundary index in your browser",
  locating: "Reading your location in your browser",
  ambiguousHeading: "More than one Seat matches — pick yours:",
  boundariesFootnote: "Boundaries per the Election Commission's 2018 delimitation.",
  noProfileYet: "MP profile not yet available",
  noMatchTag: "NO MATCH",
  noMatch: {
    "not-in-index": "Not found in the Election Commission postcode index.",
    "geolocation-unsupported": "This browser doesn't support location lookup.",
    "geolocation-denied": "Location permission was declined.",
    "geolocation-unresolvable":
      "Location was read, but this pilot has no boundary data yet to match it to a Seat — try a postcode or constituency name instead.",
    "index-unavailable":
      "The constituency index couldn't be loaded right now — check your connection or browse all seats below.",
  },
  routes: {
    searchByName: "Search by name",
    browseAllSeats: "Browse all 222 Seats",
    checkRegistration: "Check registration with SPR",
    reportMistake: "Report a mistake in this index",
  },
  seeYourMp: (seatName) => `${seatName} — see your MP →`,
  resolvedNoProfile: (seatName, state) =>
    `${seatName}, ${state} — MP profile for this Seat isn't built yet.`,
};

const MS: LookupCopy = {
  searching: "Membaca indeks sempadan dalam pelayar anda",
  locating: "Membaca lokasi dalam pelayar anda",
  ambiguousHeading: "Lebih daripada satu Kerusi sepadan — pilih Kerusi anda:",
  boundariesFootnote: "Sempadan mengikut persempadanan semula 2018 oleh Suruhanjaya Pilihan Raya.",
  noProfileYet: "Profil Ahli Parlimen belum tersedia",
  noMatchTag: "TIADA PADANAN",
  noMatch: {
    "not-in-index": "Tiada dalam indeks poskod Suruhanjaya Pilihan Raya.",
    "geolocation-unsupported": "Pelayar ini tidak menyokong carian lokasi.",
    "geolocation-denied": "Kebenaran lokasi tidak diberikan.",
    "geolocation-unresolvable":
      "Lokasi telah dibaca, tetapi perintis ini belum mempunyai data sempadan untuk memadankannya dengan Kerusi — cuba poskod atau nama kawasan.",
    "index-unavailable":
      "Indeks kawasan pilihan raya tidak dapat dimuatkan — semak sambungan anda atau lihat semua kerusi di bawah.",
  },
  routes: {
    searchByName: "Cari mengikut nama",
    browseAllSeats: "Lihat semua 222 Kerusi",
    checkRegistration: "Semak pendaftaran dengan SPR",
    reportMistake: "Laporkan kesilapan dalam indeks ini",
  },
  seeYourMp: (seatName) => `${seatName} — lihat Ahli Parlimen anda →`,
  resolvedNoProfile: (seatName, state) =>
    `${seatName}, ${state} — profil Ahli Parlimen bagi Kerusi ini belum dibina.`,
};

const COPY: Record<Language, LookupCopy> = { en: EN, ms: MS };

/** The copy table for one language. */
export function copyFor(language: Language): LookupCopy {
  return COPY[language];
}
