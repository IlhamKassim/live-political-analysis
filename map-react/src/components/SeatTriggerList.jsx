import React from "react";
import { partyColor, swatchTextColor } from "../lib/seatUtils";

/**
 * SeatTriggerList renders 10 real parliamentary constituencies as trigger cards.
 * This substitutes for the SVG map boundaries in this scoped state prototype.
 */
export function SeatTriggerList({ seats, selectedSeat, onSelectSeat }) {
  return (
    <div className="seat-trigger-grid">
      <div className="seat-trigger-head">
        <h2 style={{ fontSize: "16px", margin: "0 0 4px 0", color: "var(--ink)" }}>
          Parliamentary Constituencies (GE15)
        </h2>
        <p className="muted" style={{ margin: 0, fontSize: "12.5px" }}>
          Tap or click any seat button below to trigger the tooltip and detail panel.
        </p>
      </div>

      <div className="seat-card-list">
        {seats.map((seat) => {
          const isSelected = selectedSeat === seat.code;
          const result = seat.result || {};
          const coalition = result.coalition || "IND";
          const colColor = partyColor(coalition);
          const textColor = swatchTextColor(colColor);

          return (
            <button
              key={seat.code}
              type="button"
              className={`seat-trigger-btn ${isSelected ? "is-selected" : ""}`}
              onClick={(e) => {
                // Pass the button element bounding rect so tooltip can anchor to it
                const rect = e.currentTarget.getBoundingClientRect();
                onSelectSeat(seat.code, {
                  top: rect.top + window.scrollY,
                  left: rect.left + rect.width / 2 + window.scrollX,
                });
              }}
              style={{
                borderColor: isSelected ? "var(--select, #ffd166)" : "var(--line)",
                background: isSelected
                  ? "color-mix(in oklab, var(--select) 12%, var(--panel))"
                  : "var(--panel)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="mono" style={{ fontSize: "11px", color: "var(--accent)" }}>
                  {seat.code}
                </span>
                <span
                  className="pill"
                  style={{
                    background: colColor,
                    color: textColor,
                    fontSize: "10px",
                    padding: "1px 6px",
                  }}
                >
                  {coalition}
                </span>
              </div>

              <div style={{ textAlign: "left", marginTop: "4px" }}>
                <strong style={{ fontSize: "14px", color: "var(--ink)", display: "block" }}>
                  {seat.name}
                </strong>
                <span className="muted" style={{ fontSize: "11px" }}>
                  {seat.state}
                </span>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "11px",
                  marginTop: "6px",
                  paddingTop: "6px",
                  borderTop: "1px solid var(--line)",
                  color: "var(--ink-dim)",
                }}
              >
                <span>Majority</span>
                <span className="mono" style={{ color: "var(--ink)" }}>
                  +{result.majority?.toLocaleString()} ({result.majority_pct}%)
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
