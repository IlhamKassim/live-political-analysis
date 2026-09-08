import React, { useState, useEffect, useRef } from "react";
import { loadSeatsData, defaultSeats } from "./data/seatsData";
import { SeatTriggerList } from "./components/SeatTriggerList";
import { SeatTooltip } from "./components/SeatTooltip";
import { SeatDetailPanel } from "./components/SeatDetailPanel";
import { DismissVerificationAudit } from "./components/DismissVerificationAudit";
import "./App.css";

export default function App() {
  const [seats, setSeats] = useState(defaultSeats);
  const [selectedSeat, setSelectedSeat] = useState(null);
  const [anchorPos, setAnchorPos] = useState(null);
  const [viewportMode, setViewportMode] = useState("responsive"); // 'responsive' | 'mobile-sim'

  const [testedPaths, setTestedPaths] = useState({
    outsideClick: false,
    seatSwitch: false,
    escapeKey: false,
    panelClose: false,
  });

  const [eventLogs, setEventLogs] = useState([]);

  const containerRef = useRef(null);
  const interactiveAreaRef = useRef(null);

  const addLog = (msg, color = "var(--ink)") => {
    const time = new Date().toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    setEventLogs((prev) => [{ time, msg, color }, ...prev].slice(0, 30));
  };

  // 1. Fetch real seat dataset on mount (falls back to defaultSeats)
  useEffect(() => {
    let cancelled = false;
    loadSeatsData().then((loaded) => {
      if (!cancelled && loaded && loaded.length) {
        setSeats(loaded);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // 2. Dismiss Path: Keyboard Escape
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && selectedSeat !== null) {
        setSelectedSeat(null);
        setAnchorPos(null);
        setTestedPaths((prev) => ({ ...prev, escapeKey: true }));
        addLog(`Escape key pressed → selectedSeat reset to null`, "var(--accent)");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedSeat]);

  // 3. Dismiss Path: Outside Click (Tap elsewhere)
  const handleContainerClick = (e) => {
    if (!selectedSeat) return;

    // Check if the click target is within a seat trigger button, the detail panel, or tooltip
    const isTrigger = Boolean(e.target.closest(".seat-trigger-btn"));
    const isPanel = Boolean(e.target.closest(".bento-spot"));
    const isTooltip = Boolean(e.target.closest(".react-seat-tooltip"));

    if (!isTrigger && !isPanel && !isTooltip) {
      setSelectedSeat(null);
      setAnchorPos(null);
      setTestedPaths((prev) => ({ ...prev, outsideClick: true }));
      addLog(`Tapped elsewhere (outside click) → selectedSeat reset to null`, "var(--accent)");
    }
  };

  // 4. Select seat / Switch seat
  const handleSelectSeat = (seatCode, pos) => {
    if (selectedSeat && selectedSeat !== seatCode) {
      setTestedPaths((prev) => ({ ...prev, seatSwitch: true }));
      addLog(`Switched seat: "${selectedSeat}" → "${seatCode}" (in sync)`, "var(--accent-2)");
    } else if (selectedSeat === seatCode) {
      addLog(`Seat "${seatCode}" re-tapped`, "var(--ink-dim)");
    } else {
      addLog(`Selected seat: "${seatCode}" → Tooltip & Panel mounted`, "#4dd6c1");
    }
    setSelectedSeat(seatCode);
    setAnchorPos(pos);
  };

  // 5. Dismiss Path: Close Detail Panel (✕)
  const handleClosePanel = () => {
    setSelectedSeat(null);
    setAnchorPos(null);
    setTestedPaths((prev) => ({ ...prev, panelClose: true }));
    addLog(`Panel close button (✕) clicked → selectedSeat reset to null`, "var(--accent)");
  };

  const handleResetLogs = () => {
    setEventLogs([]);
    setTestedPaths({
      outsideClick: false,
      seatSwitch: false,
      escapeKey: false,
      panelClose: false,
    });
    addLog(`Audit logs reset`, "var(--ink-faint)");
  };

  const currentSeatObj = seats.find((s) => s.code === selectedSeat) || null;

  return (
    <div
      className={`prototype-container ${viewportMode === "mobile-sim" ? "is-mobile-sim" : ""}`}
      ref={containerRef}
      onClick={handleContainerClick}
    >
      {/* Top Bar */}
      <header className="prototype-header">
        <div className="prototype-title-group">
          <h1>PolitikKu — Map React Island Pilot</h1>
          <div className="prototype-subtitle">
            Testing declarative state management vs. mobile pinned-tooltip bug (Issue: React map migration assessment)
          </div>
        </div>

        <div className="prototype-controls">
          <div className="viewport-toggle">
            <button
              type="button"
              className={viewportMode === "responsive" ? "active" : ""}
              onClick={() => setViewportMode("responsive")}
            >
              Desktop / Fluid
            </button>
            <button
              type="button"
              className={viewportMode === "mobile-sim" ? "active" : ""}
              onClick={() => setViewportMode("mobile-sim")}
            >
              Mobile View (390px)
            </button>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <main className="prototype-body">
        {viewportMode === "mobile-sim" ? (
          /* Mobile Simulation Container */
          <div className="mobile-device-frame">
            <div className="mobile-notch-bar">
              <div className="mobile-notch-pill" />
            </div>
            <div className="mobile-inner-content" ref={interactiveAreaRef}>
              {/* Tooltip on mobile renders inline or pinned directly above the active trigger */}
              {currentSeatObj && <SeatTooltip seat={currentSeatObj} anchorPos={null} />}

              {/* Detail Panel */}
              <SeatDetailPanel seat={currentSeatObj} onClose={handleClosePanel} />

              {/* Trigger List */}
              <SeatTriggerList
                seats={seats}
                selectedSeat={selectedSeat}
                onSelectSeat={handleSelectSeat}
              />

              {/* Audit tracker inside mobile container */}
              <DismissVerificationAudit
                selectedSeat={selectedSeat}
                testedPaths={testedPaths}
                eventLogs={eventLogs}
                onResetLog={handleResetLogs}
              />
            </div>
          </div>
        ) : (
          /* Responsive Desktop Grid */
          <div className="prototype-layout-grid" ref={interactiveAreaRef}>
            {/* Column 1: Trigger List */}
            <div style={{ position: "relative" }}>
              <SeatTriggerList
                seats={seats}
                selectedSeat={selectedSeat}
                onSelectSeat={handleSelectSeat}
              />

              {/* Floating Tooltip anchored to active seat button */}
              <SeatTooltip seat={currentSeatObj} anchorPos={anchorPos} />
            </div>

            {/* Column 2: Seat Spotlight Detail Panel */}
            <div>
              <SeatDetailPanel seat={currentSeatObj} onClose={handleClosePanel} />
            </div>

            {/* Column 3: State Synchronization & Dismiss Audit Panel */}
            <div>
              <DismissVerificationAudit
                selectedSeat={selectedSeat}
                testedPaths={testedPaths}
                eventLogs={eventLogs}
                onResetLog={handleResetLogs}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
