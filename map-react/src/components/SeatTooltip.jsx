import React from "react";
import { partyColor, swatchTextColor } from "../lib/seatUtils";

/**
 * SeatTooltip component.
 *
 * CRITICAL ARCHITECTURAL GUARANTEE:
 * This component only renders if a seat object is passed to it.
 * Visibility is NOT an independent boolean flag — it is a pure projection
 * of `selectedSeat !== null`.
 *
 * When `selectedSeat === null`, this returns null and React immediately unmounts
 * the DOM element. The stuck-tooltip bug is structurally impossible.
 */
export function SeatTooltip({ seat, anchorPos }) {
  if (!seat) return null;

  const result = seat.result || {};
  const coalition = result.coalition || "IND";
  const party = result.party;
  const colColor = partyColor(coalition);
  const textColor = swatchTextColor(colColor);
  const majority = result.majority;
  const majorityPct = result.majority_pct;

  const style = anchorPos
    ? {
        position: "absolute",
        top: `${anchorPos.top}px`,
        left: `${anchorPos.left}px`,
        transform: "translate(-50%, -115%)",
        display: "block",
        zIndex: 100,
      }
    : {
        position: "relative",
        transform: "none",
        display: "block",
        margin: "0 0 12px 0",
      };

  return (
    <div id="tooltip" className="react-seat-tooltip" style={style}>
      <div className="t-statename">{seat.name}</div>
      <div className="t-code">
        {seat.code} <span className="t-state">· {seat.state}</span>
      </div>
      <div className="t-win">
        <span style={{ fontSize: "10px", opacity: 0.8 }}>GE15</span>
        <span
          className="pill"
          style={{
            background: colColor,
            color: textColor,
          }}
        >
          {coalition}
        </span>
        {party && party !== coalition && (
          <span style={{ fontSize: "11px", color: "var(--ink-dim)" }}>{party}</span>
        )}
        {majority != null && (
          <span>
            · Maj: {majority.toLocaleString()}{" "}
            {majorityPct != null ? `(${majorityPct}%)` : ""}
          </span>
        )}
      </div>
    </div>
  );
}
