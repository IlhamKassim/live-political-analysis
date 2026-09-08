// Pure domain utilities and styling helpers for PolitikKu Map React Pilot
// Extracted from and aligned with frontend/public/lib.js

export const COALITION_COLORS = {
  PH: "#d7263d",
  PN: "#15387c",
  BN: "#1f9bd6",
  GPS: "#b8332e",
  GRS: "#e8772e",
  WARISAN: "#16a085",
  KDM: "#8e44ad",
  PBM: "#6c7a89",
  BEBAS: "#8a97a6",
  STAR: "#b08a1f",
  UPKO: "#2e8b57",
  PSB: "#9b4d8a",
};

export function partyColor(p) {
  return COALITION_COLORS[(typeof p === "string" ? p : "").toUpperCase()] || "#5d6b7d";
}

function hexToRgb(hex) {
  if (typeof hex !== "string") return null;
  let s = hex.trim();
  if (s[0] === "#") s = s.slice(1);
  if (/^[0-9a-fA-F]{3}$/.test(s)) s = s.split("").map((c) => c + c).join("");
  if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
  const n = Number.parseInt(s, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function relLum(rgb) {
  const channels = rgb.map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrastRatio(a, b) {
  const l1 = relLum(a);
  const l2 = relLum(b);
  const hi = Math.max(l1, l2);
  const lo = Math.min(l1, l2);
  return (hi + 0.05) / (lo + 0.05);
}

export function swatchTextColor(bg) {
  const rgb = hexToRgb(bg);
  if (!rgb) return "#fff";
  const white = [255, 255, 255];
  const ink = [5, 7, 12];
  return contrastRatio(ink, rgb) >= contrastRatio(white, rgb) ? "#05070c" : "#fff";
}

export function competitivenessFromMajorityPct(mp) {
  if (!Number.isFinite(mp) || mp < 0) return null;
  return { key: mp < 5 ? "marginal" : mp < 15 ? "leaning" : "safe", pct: mp };
}

export function personInitials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  const first = parts[0][0] || "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export function monogramColor(name) {
  let h = 0;
  for (let i = 0; i < (name || "").length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360} 42% 40%)`;
}
