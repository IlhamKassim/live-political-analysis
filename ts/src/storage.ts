// "Recently looked up" chips, seeded from localStorage, most recent first,
// capped at four — design_handoff_politikku/README.md's own wording.

const STORAGE_KEY = "pk-recent-seats";
const MAX_RECENT = 4;

export interface RecentSeat {
  readonly code: string;
  readonly name: string;
}

/** Reads the recent-Seats list, newest first. Never throws: a private
 * window, cleared site data, or a browser that blocks storage should just
 * read back an empty list, not break the page. */
export function readRecentSeats(): readonly RecentSeat[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isRecentSeat).slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

/** Records `seat` as the most recent lookup, moving it to the front if it
 * was already present, and trims to `MAX_RECENT`. */
export function recordRecentSeat(seat: RecentSeat): void {
  try {
    const existing = readRecentSeats().filter((s) => s.code !== seat.code);
    const next = [seat, ...existing].slice(0, MAX_RECENT);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage can throw (quota, private mode, disabled) — a failed write
    // here must not break the lookup that triggered it.
  }
}

function isRecentSeat(value: unknown): value is RecentSeat {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { code?: unknown }).code === "string" &&
    typeof (value as { name?: unknown }).name === "string"
  );
}
