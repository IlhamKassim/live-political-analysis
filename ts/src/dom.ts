// Mounts the lookup state machine onto the Python-rendered markup from
// politikku_homepage.py/politikku_landing.py — `data-pk-lookup-form` and
// its siblings already exist server-side (#74); this file wires behaviour
// onto them and owns the one piece those pages don't pre-render: the
// dynamic results area for `searching`/`locating`/`ambiguous`/`notFound`/
// `resolved` (`[data-pk-lookup-results]`, added alongside the form in both
// pages' shared markup for this ticket).
//
// Every string this file draws comes from `i18n.ts`, in whichever language
// `<html lang>` says (#82) — this results area is the only part of
// PolitikKu whose BM copy is not rendered server-side, because it is the
// only part Python never renders at all.
//
// The "narrow down by street name or Seksyen" field the mock draws for the
// ambiguous state is not built here: this pilot's index (ADR 0008) has no
// street-level data to narrow anything with, and a text field that quietly
// does nothing would claim a capability that does not exist — the same
// honesty call #74/#75/#79 made for their own data gaps. The two (today,
// at most a handful) candidate rows are picked directly instead.

import { locate } from "./geolocation";
import { copyFor, currentLanguage, type LookupCopy } from "./i18n";
import { loadClientIndex } from "./index-data";
import { resolveQuery } from "./resolve";
import { readRecentSeats, recordRecentSeat } from "./storage";
import { initialModel, transition, type LookupModel } from "./state-machine";
import type { ClientLookupIndex, LookupSeat, NoMatchReason } from "./types";

interface Refs {
  readonly form: HTMLFormElement;
  readonly input: HTMLInputElement;
  readonly locateButton: HTMLButtonElement | null;
  readonly results: HTMLElement | null;
  readonly recentChips: HTMLElement | null;
  readonly recentList: HTMLElement | null;
}

// Must stay in step with politikku_shell.MP_PROFILE_DIR under
// POLITIKKU_PREFIX (issue #104 moved both to the site root) — this is the
// same href politikku_mp_profile writes its pages at, built in the browser,
// where that constant cannot be imported.
function mpProfileUrl(code: string): string {
  return `/mp/${encodeURIComponent(code)}.html`;
}

function findRefs(container: HTMLElement): Refs | null {
  const form = container.querySelector<HTMLFormElement>("[data-pk-lookup-form]");
  const input = container.querySelector<HTMLInputElement>("[data-pk-lookup-input]");
  if (!form || !input) return null;
  return {
    form,
    input,
    locateButton: container.querySelector<HTMLButtonElement>("[data-pk-locate]"),
    results: container.querySelector<HTMLElement>("[data-pk-lookup-results]"),
    recentChips: container.querySelector<HTMLElement>("[data-pk-recent-chips]"),
    recentList: container.querySelector<HTMLElement>("[data-pk-recent-list]"),
  };
}

/** Finds every lookup form on the page and mounts a controller for each. */
export function mountAllLookups(root: ParentNode = document): void {
  const containers = new Set<HTMLElement>();
  for (const form of root.querySelectorAll<HTMLFormElement>("[data-pk-lookup-form]")) {
    const container = form.closest<HTMLElement>("[data-pk-lookup-scope]") ?? form.parentElement;
    if (container) containers.add(container);
  }
  for (const container of containers) mountLookup(container);
}

export function mountLookup(container: HTMLElement): void {
  const maybeRefs = findRefs(container);
  if (!maybeRefs) return;
  const refs: Refs = maybeRefs;

  let model: LookupModel = initialModel;

  function setModel(next: LookupModel): void {
    model = next;
    render(refs, model, resetToIdle);
  }

  function resetToIdle(): void {
    refs.input.value = "";
    refs.input.focus();
    setModel(transition(model, { type: "reset" }));
  }

  refs.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = refs.input.value;
    setModel(transition(model, { type: "submitQuery", query }));
    // Awaited here, not before mounting: this is the module's one real
    // network read, so the `searching` skeleton's status text ("Reading
    // the boundary index in your browser") is only ever shown while this
    // is genuinely still pending — usually never, once the index is
    // cached from an earlier lookup on the page.
    void loadClientIndex()
      .then((index) => {
        const result = resolveQuery(query, index);
        if (result.kind === "resolved") {
          recordRecentSeat({ code: result.seat.code, name: result.seat.name });
        }
        setModel(transition(model, { type: "resolved", result }));
        if (result.kind === "resolved") renderRecentChips(refs, index);
      })
      .catch(() => {
        setModel(
          transition(model, {
            type: "resolved",
            result: { kind: "notFound", reason: "index-unavailable" },
          }),
        );
      });
  });

  refs.locateButton?.addEventListener("click", () => {
    setModel(transition(model, { type: "requestLocation" }));
    void locate().then((result) => {
      setModel(transition(model, { type: "resolved", result }));
    });
  });

  void loadClientIndex()
    .then((index) => renderRecentChips(refs, index))
    .catch(() => {
      // Quietly skip rendering recent chips if index load fails at mount time.
    });
}

function renderRecentChips(refs: Refs, index: ClientLookupIndex): void {
  if (!refs.recentChips || !refs.recentList) return;
  const recent = readRecentSeats().filter((seat) => seat.code in index.seats);
  refs.recentChips.hidden = recent.length === 0;
  refs.recentList.replaceChildren(
    ...recent.map((seat) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "pk-recent-chip";
      chip.textContent = seat.name;
      chip.addEventListener("click", () => {
        refs.input.value = seat.name;
        refs.form.requestSubmit();
      });
      return chip;
    }),
  );
}

function render(refs: Refs, model: LookupModel, onSearchByName: () => void): void {
  // README: "the input border turns #c9a86a" for a text-query no-match —
  // the search field itself, not just the results area. Only for
  // `not-in-index`: a geolocation reason didn't come from anything typed
  // into this input, so it has nothing to flag.
  refs.input.classList.toggle(
    "pk-lookup-input-error",
    model.state === "notFound" && model.result?.kind === "notFound" && model.result.reason === "not-in-index",
  );

  if (!refs.results) return;
  // Read per render, not once at mount: nothing here caches a language, so
  // the results area always speaks whatever `<html lang>` says at the
  // moment it draws.
  const copy = copyFor(currentLanguage());
  refs.results.hidden = model.state === "idle";
  refs.results.replaceChildren();
  switch (model.state) {
    case "idle":
      return;
    case "searching":
      refs.results.append(skeleton(copy.searching));
      return;
    case "locating":
      refs.results.append(skeleton(copy.locating));
      return;
    case "ambiguous":
      if (model.result?.kind === "ambiguous") {
        refs.results.append(ambiguousView(model.result.candidates, copy));
      }
      return;
    case "notFound":
      if (model.result?.kind === "notFound") {
        refs.results.append(notFoundView(model.result.reason, onSearchByName, copy));
      }
      return;
    case "resolved":
      if (model.result?.kind === "resolved") {
        refs.results.append(resolvedView(model.result.seat, copy));
      }
      return;
  }
}

function skeleton(statusText: string): HTMLElement {
  const el = document.createElement("div");
  el.className = "pk-lookup-skeleton";
  el.setAttribute("role", "status");
  const bars = document.createElement("div");
  bars.className = "pk-lookup-skeleton-bars";
  bars.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i++) {
    const bar = document.createElement("div");
    bar.className = "pk-lookup-skeleton-bar";
    bars.append(bar);
  }
  const status = document.createElement("p");
  status.className = "pk-lookup-status";
  status.textContent = statusText;
  el.append(bars, status);
  return el;
}

function ambiguousView(candidates: readonly LookupSeat[], copy: LookupCopy): HTMLElement {
  const el = document.createElement("div");
  el.className = "pk-lookup-ambiguous";
  const heading = document.createElement("p");
  heading.className = "pk-lookup-ambiguous-heading";
  heading.textContent = copy.ambiguousHeading;
  el.append(heading);
  const list = document.createElement("div");
  list.className = "pk-lookup-candidate-list";
  for (const seat of candidates) {
    list.append(candidateRow(seat, copy));
  }
  const footnote = document.createElement("p");
  footnote.className = "pk-lookup-footnote";
  footnote.textContent = copy.boundariesFootnote;
  el.append(list, footnote);
  return el;
}

function candidateRow(seat: LookupSeat, copy: LookupCopy): HTMLElement {
  const row = document.createElement("a");
  row.className = "pk-lookup-candidate";
  row.href = seat.hasProfile ? mpProfileUrl(seat.code) : "#";
  if (!seat.hasProfile) {
    row.setAttribute("aria-disabled", "true");
    row.addEventListener("click", (event) => event.preventDefault());
  }
  const code = document.createElement("span");
  code.className = "pk-lookup-candidate-code";
  code.textContent = seat.code;
  const name = document.createElement("span");
  name.className = "pk-lookup-candidate-name";
  name.textContent = `${seat.name}, ${seat.state}`;
  const mp = document.createElement("span");
  mp.className = "pk-lookup-candidate-mp";
  mp.textContent = seat.hasProfile && seat.mpName ? seat.mpName : copy.noProfileYet;
  row.append(code, name, mp);
  return row;
}

// README's "No match" state names four routes out — three named links plus
// "a public corrections link" — and requires "search by name" to be a real
// route, not decoration. There is no third-party corrections form to point
// at (this pilot's postcode index is this project's own, open-source
// data), so the corrections link goes to this repo's own issue tracker —
// the same "fork it, disagree with it" openness the landing page already
// states, applied to the one dataset a member of the public could
// concretely find wrong.
const CORRECTIONS_URL =
  "https://github.com/IlhamKassim/live-political-analysis/issues/new?title=Postcode%20index%20correction";

// Which routes out each no-match reason offers (#82).
//
// `not-in-index` keeps all four, unchanged from #77. `geolocation-denied`
// gets the two that are about finding a Seat at all — the text search this
// state falls back to, and the full list of 222 — and not the two that are
// about the postcode index specifically ("Check registration with SPR",
// "Report a mistake in this index"): a declined permission never consulted
// that index, so pointing at its corrections form would invite a report
// about a dataset that had nothing to do with what just happened.
//
// The other two geolocation reasons stay bare on purpose.
// `geolocation-unresolvable` already names its own way forward inside its
// message ("try a postcode or constituency name instead") and a routes list
// under it would say the same thing twice; `geolocation-unsupported` is
// outside this ticket's scope (#82 scopes the permission-denied state), so
// it is left as #77 shipped it rather than redesigned in passing.
//
// Nothing here touches `pk-lookup-input-error`: that amber input border
// flags a typed query the index rejected, and a geolocation failure is not
// a typing mistake. The container's own `pk-lookup-not-found` caution
// border is the whole visual treatment — no error-red anywhere, per the
// tone rule #77 set.
const ROUTES_BY_REASON: Record<NoMatchReason, readonly RouteId[]> = {
  "not-in-index": ["searchByName", "browseAllSeats", "checkRegistration", "reportMistake"],
  "geolocation-denied": ["searchByName", "browseAllSeats"],
  "geolocation-unsupported": [],
  "geolocation-unresolvable": [],
  "index-unavailable": ["browseAllSeats"],
};

type RouteId = "searchByName" | "browseAllSeats" | "checkRegistration" | "reportMistake";

const ROUTE_HREFS: Record<Exclude<RouteId, "searchByName">, string> = {
  browseAllSeats: "/",
  checkRegistration: "https://daftarj.spr.gov.my/",
  reportMistake: CORRECTIONS_URL,
};

function notFoundView(
  reason: NoMatchReason,
  onSearchByName: () => void,
  copy: LookupCopy,
): HTMLElement {
  const el = document.createElement("div");
  el.className = "pk-lookup-not-found";
  const tag = document.createElement("span");
  tag.className = "pk-lookup-no-match-tag";
  tag.textContent = copy.noMatchTag;
  const message = document.createElement("p");
  message.className = "pk-lookup-no-match-reason";
  message.textContent = copy.noMatch[reason];
  el.append(tag, message);

  const routeIds = ROUTES_BY_REASON[reason];
  if (routeIds.length > 0) {
    const routes = document.createElement("ul");
    routes.className = "pk-lookup-routes";
    for (const id of routeIds) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.textContent = copy.routes[id];
      if (id === "searchByName") {
        // The text field itself never went away — this link only puts the
        // cursor back in it, which is the whole fallback this state needs.
        a.href = "#";
        a.addEventListener("click", (event) => {
          event.preventDefault();
          onSearchByName();
        });
      } else {
        a.href = ROUTE_HREFS[id];
      }
      li.append(a);
      routes.append(li);
    }
    el.append(routes);
  }
  return el;
}

function resolvedView(seat: LookupSeat, copy: LookupCopy): HTMLElement {
  const el = document.createElement("div");
  el.className = "pk-lookup-resolved";
  if (seat.hasProfile) {
    const link = document.createElement("a");
    link.className = "pk-lookup-resolved-link";
    link.href = mpProfileUrl(seat.code);
    link.textContent = copy.seeYourMp(seat.name);
    el.append(link);
  } else {
    const p = document.createElement("p");
    p.className = "pk-lookup-resolved-no-profile";
    p.textContent = copy.resolvedNoProfile(seat.name, seat.state);
    el.append(p);
  }
  return el;
}
