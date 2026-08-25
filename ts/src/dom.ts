// Mounts the lookup state machine onto the Python-rendered markup from
// politikku_homepage.py/politikku_landing.py — `data-pk-lookup-form` and
// its siblings already exist server-side (#74); this file wires behaviour
// onto them and owns the one piece those pages don't pre-render: the
// dynamic results area for `searching`/`locating`/`ambiguous`/`notFound`/
// `resolved` (`[data-pk-lookup-results]`, added alongside the form in both
// pages' shared markup for this ticket).
//
// The "narrow down by street name or Seksyen" field the mock draws for the
// ambiguous state is not built here: this pilot's index (ADR 0008) has no
// street-level data to narrow anything with, and a text field that quietly
// does nothing would claim a capability that does not exist — the same
// honesty call #74/#75/#79 made for their own data gaps. The two (today,
// at most a handful) candidate rows are picked directly instead.

import { locate } from "./geolocation";
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

function mpProfileUrl(code: string): string {
  return `/politikku/mp/${encodeURIComponent(code)}.html`;
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
    void loadClientIndex().then((index) => {
      const result = resolveQuery(query, index);
      if (result.kind === "resolved") {
        recordRecentSeat({ code: result.seat.code, name: result.seat.name });
      }
      setModel(transition(model, { type: "resolved", result }));
      if (result.kind === "resolved") renderRecentChips(refs, index);
    });
  });

  refs.locateButton?.addEventListener("click", () => {
    setModel(transition(model, { type: "requestLocation" }));
    void locate().then((result) => {
      setModel(transition(model, { type: "resolved", result }));
    });
  });

  void loadClientIndex().then((index) => renderRecentChips(refs, index));
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
  refs.results.hidden = model.state === "idle";
  refs.results.replaceChildren();
  switch (model.state) {
    case "idle":
      return;
    case "searching":
      refs.results.append(skeleton("Reading the boundary index in your browser"));
      return;
    case "locating":
      refs.results.append(skeleton("Reading your location in your browser"));
      return;
    case "ambiguous":
      if (model.result?.kind === "ambiguous") {
        refs.results.append(ambiguousView(model.result.candidates));
      }
      return;
    case "notFound":
      if (model.result?.kind === "notFound") {
        refs.results.append(notFoundView(model.result.reason, onSearchByName));
      }
      return;
    case "resolved":
      if (model.result?.kind === "resolved") {
        refs.results.append(resolvedView(model.result.seat));
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

function ambiguousView(candidates: readonly LookupSeat[]): HTMLElement {
  const el = document.createElement("div");
  el.className = "pk-lookup-ambiguous";
  const heading = document.createElement("p");
  heading.className = "pk-lookup-ambiguous-heading";
  heading.textContent = "More than one Seat matches — pick yours:";
  el.append(heading);
  const list = document.createElement("div");
  list.className = "pk-lookup-candidate-list";
  for (const seat of candidates) {
    list.append(candidateRow(seat));
  }
  const footnote = document.createElement("p");
  footnote.className = "pk-lookup-footnote";
  footnote.textContent = "Boundaries per the Election Commission's 2018 delimitation.";
  el.append(list, footnote);
  return el;
}

function candidateRow(seat: LookupSeat): HTMLElement {
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
  mp.textContent = seat.hasProfile && seat.mpName ? seat.mpName : "MP profile not yet available";
  row.append(code, name, mp);
  return row;
}

const NO_MATCH_COPY: Record<NoMatchReason, string> = {
  "not-in-index": "Not found in the Election Commission postcode index.",
  "geolocation-unsupported": "This browser doesn't support location lookup.",
  "geolocation-denied": "Location permission was declined.",
  "geolocation-unresolvable":
    "Location was read, but this pilot has no boundary data yet to match it to a Seat — try a postcode or constituency name instead.",
};

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

function notFoundView(reason: NoMatchReason, onSearchByName: () => void): HTMLElement {
  const el = document.createElement("div");
  el.className = "pk-lookup-not-found";
  const tag = document.createElement("span");
  tag.className = "pk-lookup-no-match-tag";
  tag.textContent = "NO MATCH";
  const message = document.createElement("p");
  message.className = "pk-lookup-no-match-reason";
  message.textContent = NO_MATCH_COPY[reason];
  el.append(tag, message);
  if (reason === "not-in-index") {
    const routes = document.createElement("ul");
    routes.className = "pk-lookup-routes";

    const searchByName = document.createElement("li");
    const searchByNameLink = document.createElement("a");
    searchByNameLink.href = "#";
    searchByNameLink.textContent = "Search by name";
    searchByNameLink.addEventListener("click", (event) => {
      event.preventDefault();
      onSearchByName();
    });
    searchByName.append(searchByNameLink);
    routes.append(searchByName);

    for (const [label, href] of [
      ["Browse all 222 Seats", "/"],
      ["Check registration with SPR", "https://daftarj.spr.gov.my/"],
      ["Report a mistake in this index", CORRECTIONS_URL],
    ] as const) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = href;
      a.textContent = label;
      li.append(a);
      routes.append(li);
    }
    el.append(routes);
  }
  return el;
}

function resolvedView(seat: LookupSeat): HTMLElement {
  const el = document.createElement("div");
  el.className = "pk-lookup-resolved";
  if (seat.hasProfile) {
    const link = document.createElement("a");
    link.className = "pk-lookup-resolved-link";
    link.href = mpProfileUrl(seat.code);
    link.textContent = `${seat.name} — see your MP →`;
    el.append(link);
  } else {
    const p = document.createElement("p");
    p.className = "pk-lookup-resolved-no-profile";
    p.textContent = `${seat.name}, ${seat.state} — MP profile for this Seat isn't built yet.`;
    el.append(p);
  }
  return el;
}
