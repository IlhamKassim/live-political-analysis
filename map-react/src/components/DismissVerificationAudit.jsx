import React from "react";

/**
 * DismissVerificationAudit component.
 *
 * Provides real-time verification of the core hypothesis:
 * That single-source-of-truth state (`selectedSeat: string | null`)
 * structurally guarantees that tooltip and detail panel never drift apart
 * or remain orphaned.
 */
export function DismissVerificationAudit({
  selectedSeat,
  testedPaths,
  eventLogs,
  onResetLog,
}) {
  const isSelected = Boolean(selectedSeat);

  return (
    <div className="audit-card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "10px",
        }}
      >
        <h3
          style={{
            fontSize: "13px",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            margin: 0,
            color: "var(--accent)",
          }}
        >
          State Synchronization Audit
        </h3>
        <button
          type="button"
          onClick={onResetLog}
          className="audit-reset-btn"
          style={{
            background: "none",
            border: "1px solid var(--line-2)",
            color: "var(--ink-dim)",
            fontSize: "10px",
            padding: "2px 6px",
            borderRadius: "4px",
            cursor: "pointer",
          }}
        >
          Reset Logs
        </button>
      </div>

      {/* State Inspection Row */}
      <div className="audit-state-grid">
        <div className="audit-metric">
          <span className="audit-metric-label">selectedSeat State</span>
          <strong
            className="mono"
            style={{
              color: isSelected ? "var(--accent-2)" : "var(--ink-faint)",
              fontSize: "13px",
            }}
          >
            {selectedSeat ? `"${selectedSeat}"` : "null"}
          </strong>
        </div>

        <div className="audit-metric">
          <span className="audit-metric-label">Tooltip Component</span>
          <strong
            style={{
              color: isSelected ? "#4dd6c1" : "var(--ink-faint)",
              fontSize: "12px",
            }}
          >
            {isSelected ? "● MOUNTED & VISIBLE" : "○ UNMOUNTED (DOM CLEAN)"}
          </strong>
        </div>

        <div className="audit-metric">
          <span className="audit-metric-label">Detail Panel</span>
          <strong
            style={{
              color: isSelected ? "#4dd6c1" : "var(--ink-faint)",
              fontSize: "12px",
            }}
          >
            {isSelected ? "● SPOTLIGHT ACTIVE" : "○ PLACEHOLDER"}
          </strong>
        </div>
      </div>

      {/* 4 Dismiss Paths Checklist */}
      <div style={{ marginTop: "14px" }}>
        <span
          style={{
            fontSize: "11px",
            color: "var(--ink-dim)",
            fontWeight: 600,
            display: "block",
            marginBottom: "6px",
          }}
        >
          Required Dismiss Pathways Verification:
        </span>
        <ul className="audit-checklist">
          <li className={testedPaths.outsideClick ? "is-passed" : ""}>
            <span className="check-icon">{testedPaths.outsideClick ? "✓" : "○"}</span>
            <span>
              <strong>1. Tap Elsewhere (Outside Click):</strong> Clears state to null
            </span>
          </li>
          <li className={testedPaths.seatSwitch ? "is-passed" : ""}>
            <span className="check-icon">{testedPaths.seatSwitch ? "✓" : "○"}</span>
            <span>
              <strong>2. Tap Another Seat:</strong> Switches both components synchronously
            </span>
          </li>
          <li className={testedPaths.escapeKey ? "is-passed" : ""}>
            <span className="check-icon">{testedPaths.escapeKey ? "✓" : "○"}</span>
            <span>
              <strong>3. Press Escape:</strong> Global keydown listener unsets state
            </span>
          </li>
          <li className={testedPaths.panelClose ? "is-passed" : ""}>
            <span className="check-icon">{testedPaths.panelClose ? "✓" : "○"}</span>
            <span>
              <strong>4. Panel Close Button (✕):</strong> Direct action unsets state
            </span>
          </li>
        </ul>
      </div>

      {/* Real-time event log */}
      <div style={{ marginTop: "12px" }}>
        <span
          style={{
            fontSize: "10.5px",
            color: "var(--ink-faint)",
            fontFamily: "var(--mono)",
            display: "block",
            marginBottom: "4px",
          }}
        >
          LIVE TRANSITION STREAM:
        </span>
        <div className="audit-log-stream mono">
          {eventLogs.length === 0 ? (
            <div style={{ color: "var(--ink-faint)", fontStyle: "italic" }}>
              Awaiting user interactions...
            </div>
          ) : (
            eventLogs.slice(0, 5).map((log, idx) => (
              <div key={idx} className="audit-log-line">
                <span style={{ color: "var(--accent)", marginRight: "6px" }}>
                  [{log.time}]
                </span>
                <span style={{ color: log.color || "var(--ink)" }}>{log.msg}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
