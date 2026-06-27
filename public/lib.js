// MyPolitik — pure, DOM-free logic shared by the app and the test suite.
// Everything here must run unchanged in the browser AND under `node --test`,
// so: no `document`, no `window`, no `location` — inputs in, values out.

// ---- shareable URL state  (#tier/mode[/code]) ----
// encodeHash builds the location hash from app state; decodeHash parses one
// back. Faithful extraction of app.js's old writeHash/parseHash internals —
// same encoding, same field order, same null-on-empty contract.

export function encodeHash(state) {
  const parts = [state.tier, state.mode];
  if (state.selected) parts.push(state.selected);
  return "#" + parts.map(encodeURIComponent).join("/");
}

export function decodeHash(hash) {
  const raw = String(hash == null ? "" : hash).replace(/^#/, "");
  if (!raw) return null;
  const [tier, mode, code] = raw.split("/").map((s) => decodeURIComponent(s || ""));
  return { tier, mode, code };
}
