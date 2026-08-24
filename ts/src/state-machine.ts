// The lookup's typed state machine — pure and synchronous, so every
// transition is testable without a DOM or a real network/geolocation call.
// `dom.ts` is the only place that calls `resolveQuery`/`locate` and feeds
// their result back in as a `resolved` action; this file never calls
// either itself.

import type { LookupState, ResolutionResult } from "./types";

export interface LookupModel {
  readonly state: LookupState;
  /** The text currently in the input, kept here (not just read from the
   * DOM) so a transition can be asserted against it in a test. */
  readonly query: string;
  /** The last resolution outcome — `null` in `idle`/`locating`/`searching`,
   * set for `ambiguous`/`notFound`/`resolved`. */
  readonly result: ResolutionResult | null;
}

export type LookupAction =
  | { readonly type: "submitQuery"; readonly query: string }
  | { readonly type: "requestLocation" }
  | { readonly type: "resolved"; readonly result: ResolutionResult }
  | { readonly type: "reset" };

export const initialModel: LookupModel = { state: "idle", query: "", result: null };

/** One transition. Never throws — an action that doesn't make sense in the
 * current state (there are none today, since every state accepts every
 * action per the design's own diagram) is accepted rather than silently
 * dropped, so a caller can always trust the returned model reflects the
 * action it just sent. */
export function transition(model: LookupModel, action: LookupAction): LookupModel {
  switch (action.type) {
    case "submitQuery":
      return { state: "searching", query: action.query, result: null };
    case "requestLocation":
      return { state: "locating", query: model.query, result: null };
    case "resolved":
      return { state: action.result.kind, query: model.query, result: action.result };
    case "reset":
      return initialModel;
  }
}
