import React, { useState } from "react";
import {
  partyColor,
  swatchTextColor,
  competitivenessFromMajorityPct,
  personInitials,
  monogramColor,
} from "../lib/seatUtils";

/**
 * SeatDetailPanel component ("Seat spotlight" bento tile).
 *
 * Displays the current YB, party affiliations, GE15 vote margin bar, and Wikipedia bio.
 * Includes a close button (✕) that directly unsets selectedSeat.
 */
export function SeatDetailPanel({ seat, onClose }) {
  const [photoError, setPhotoError] = useState(false);

  if (!seat) {
    return (
      <article className="bento-tile bento-spot">
        <div className="bento-spot-empty">
          <div className="bento-spot-mark">🗺️</div>
          <p className="muted" style={{ margin: 0, fontSize: "14px" }}>
            Tap or click any seat on the left to spotlight the constituency details and tooltip.
          </p>
        </div>
      </article>
    );
  }

  const result = seat.result || {};
  const mp = seat.mp || {};
  const ybName = mp.name || result.name || "Unknown";
  const coalition = mp.coalition || result.coalition || "IND";
  const party = mp.party || result.party;
  const colColor = partyColor(coalition);
  const textColor = swatchTextColor(colColor);
  const partyLabel = party && party !== coalition ? party : "";

  const votePct = result.vote_pct;
  const majority = result.majority;
  const majorityPct = result.majority_pct;
  const turnout = result.turnout;
  const votes = result.votes;
  const comp = competitivenessFromMajorityPct(majorityPct);
  const runnerUp = result.runner_up;

  const bio = mp.wikipedia?.en || mp.wikipedia?.ms;
  const hasPhoto = mp.photo && !photoError;

  return (
    <article className="bento-tile bento-spot" style={{ position: "relative" }}>
      {/* Header bar with close button */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "12px",
        }}
      >
        <div className="bento-spot-head">
          <div className="bento-spot-kicker">{seat.code} · PARLIMEN</div>
          <h3 style={{ fontSize: "20px", margin: "2px 0 0", color: "var(--ink)" }}>
            {seat.name}
          </h3>
          <span className="bento-spot-meta muted">{seat.state}</span>
        </div>

        {/* Close button that clears selectedSeat */}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close detail panel"
          title="Close detail panel (Dismisses both panel and tooltip)"
          style={{
            background: "var(--bg-2, #11151d)",
            border: "1px solid var(--line, #1d2733)",
            color: "var(--ink-dim, #93a1b3)",
            width: "32px",
            height: "32px",
            borderRadius: "8px",
            display: "grid",
            placeItems: "center",
            cursor: "pointer",
            fontSize: "14px",
            lineHeight: 1,
            flexShrink: 0,
            transition: "all 0.15s ease",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "var(--ink)";
            e.currentTarget.style.borderColor = "var(--accent)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--ink-dim)";
            e.currentTarget.style.borderColor = "var(--line)";
          }}
        >
          ✕
        </button>
      </div>

      {/* YB Card */}
      <div className="seat-yb-card has-profile" style={{ marginTop: "8px" }}>
        <div className="yb-head">
          {hasPhoto ? (
            <img
              className="pol-photo yb-photo"
              src={mp.photo}
              alt={ybName}
              width="72"
              height="72"
              onError={() => setPhotoError(true)}
              style={{ objectFit: "cover" }}
            />
          ) : (
            <span
              className="pol-photo pol-fallback pol-monogram yb-photo"
              aria-hidden="true"
              style={{ background: monogramColor(ybName) }}
            >
              <svg
                className="pol-fallback-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span className="pol-fallback-initials">{personInitials(ybName)}</span>
            </span>
          )}

          <div className="yb-id">
            <span className="yb-kicker">Current YB / Ahli Parlimen</span>
            <strong style={{ fontSize: "16px" }}>{ybName}</strong>
            <p style={{ margin: "3px 0 0" }}>
              {partyLabel && <span>{partyLabel} </span>}
              <span className="bloc-unit">
                {partyLabel && "· "}
                <span
                  className="pill"
                  style={{
                    background: colColor,
                    color: textColor,
                    padding: "2px 8px",
                    borderRadius: "999px",
                    fontSize: "11px",
                    fontWeight: "600",
                  }}
                >
                  {coalition}
                </span>
              </span>
            </p>
          </div>
        </div>

        {bio && (
          <div className="yb-bio" style={{ marginTop: "8px" }}>
            <p className="yb-bio-text">{bio.extract}</p>
            {bio.url && (
              <a
                className="yb-bio-more"
                href={bio.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--accent)" }}
              >
                Wikipedia →
              </a>
            )}
          </div>
        )}
      </div>

      {/* GE15 Last Result block */}
      <div className="prn-inc bento-spot-result" style={{ marginTop: "12px" }}>
        <div className="prn-inc-top">
          <span className="prn-inc-kicker">GE15 Result</span>
          {comp && (
            <span className={`prn-comp prn-comp-${comp.key}`}>
              {comp.key.toUpperCase()} ({comp.pct}%)
            </span>
          )}
        </div>

        {Number.isFinite(votePct) && (
          <div className="prn-margin-bar" style={{ margin: "8px 0 6px" }}>
            <span
              style={{
                width: `${Math.min(100, votePct)}%`,
                background: colColor,
              }}
            />
          </div>
        )}

        <div className="prn-inc-stat muted">
          {votes != null && `${votes.toLocaleString()} votes (${votePct}%)`}
          {majority != null && ` · Won by ${majority.toLocaleString()} (${majorityPct}%)`}
          {turnout != null && ` · Turnout ${turnout}%`}
        </div>

        {runnerUp && runnerUp.name && (
          <div className="bento-spot-runner muted" style={{ marginTop: "6px" }}>
            Runner-up: {runnerUp.name} {runnerUp.party ? `(${runnerUp.party})` : ""}
            {runnerUp.votes != null ? ` · ${runnerUp.votes.toLocaleString()} votes` : ""}
          </div>
        )}
      </div>
    </article>
  );
}
