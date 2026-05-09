// Modal — full spool drill-in
const { useState: useStateMod, useEffect: useEffectMod } = React;

function SpoolModal({ open, spool, unit, onClose }) {
  useEffectMod(() => {
    function onKey(e) { if (e.key === "Escape") onClose(); }
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const isEmpty = !spool;
  const palette = spool ? SPOOL_PALETTE[spool.color] : null;
  const remainingPct = spool ? Math.round(spool.remaining * 100) : 0;
  const remainingG = spool ? Math.round(spool.remaining * spool.weight) : 0;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        {isEmpty ? (
          <div className="modal-empty">
            <div className="modal-empty-icon">⌀</div>
            <h2>Empty bay</h2>
            <p className="muted">No spool detected in {unit?.label}. Drop in an RFID-tagged spool to begin tracking.</p>
            <button className="btn btn-primary" onClick={onClose}>Close</button>
          </div>
        ) : (
          <>
            <div className="modal-hero" style={{
              background: `radial-gradient(circle at 30% 30%, ${palette.hex}33, transparent 60%), var(--surface-2)`,
            }}>
              <div className="modal-hero-spool">
                <Spool color={palette.hex} accent={palette.accent} remaining={spool.remaining} size="ht" />
              </div>
              <div className="modal-hero-meta">
                <div className="modal-eyebrow">{unit?.label} · Slot {spool.slot + 1}</div>
                <h2 className="modal-title">{spool.material}</h2>
                <div className="modal-sub">
                  <span className="dot" style={{ background: palette.hex }} />
                  {palette.name} · {spool.brand}
                </div>
              </div>
            </div>

            <div className="modal-body">
              <div className="stat-grid">
                <div className="stat">
                  <div className="stat-label">Remaining</div>
                  <div className="stat-value">{remainingPct}<span>%</span></div>
                  <div className="bar">
                    <div className="bar-fill" style={{ width: remainingPct + "%", background: palette.hex }} />
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-label">Estimate</div>
                  <div className="stat-value">{remainingG}<span>g</span></div>
                  <div className="muted small">of {spool.weight}g nominal</div>
                </div>
                <div className="stat">
                  <div className="stat-label">RFID</div>
                  <div className="stat-value mono">{spool.rfid}</div>
                  <div className="muted small">verified · last scan {spool.lastUsed}</div>
                </div>
                <div className="stat">
                  <div className="stat-label">Status</div>
                  <div className="stat-value">{spool.active ? "Printing" : "Idle"}</div>
                  <div className="muted small">{spool.active ? "Currently feeding" : "Ready to feed"}</div>
                </div>
              </div>

              <div className="modal-actions">
                <button className="btn">Mark spent</button>
                <button className="btn">Recalibrate weight</button>
                <button className="btn btn-primary">Set as active</button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

window.SpoolModal = SpoolModal;
