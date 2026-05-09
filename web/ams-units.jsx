// AMS unit visualizations — stylized-realistic but ORIGINAL design.
// Not a copy of any branded product. Workshop-warm aesthetic.

const { useMemo } = React;

// ──────────────────────────────────────────────────────────────────────
// Spool — front view (looks like a spool seen from the side, color-banded)
// ──────────────────────────────────────────────────────────────────────
function Spool({ color, accent, remaining = 1, size = "regular", spinning = false }) {
  const dims = size === "ht"
    ? { w: 110, h: 110, rim: 18, hole: 14 }
    : { w: 96, h: 96, rim: 16, hole: 12 };

  // Filament shows through more as remaining decreases — visualize by reducing the
  // "wound material" radius. Min radius is the empty cardboard core.
  const innerR = dims.w / 2 - dims.rim;
  const coreR = dims.hole + 6;
  const woundR = coreR + (innerR - coreR) * remaining;

  return (
    <div className="spool" style={{
      width: dims.w, height: dims.h,
      "--spool-color": color,
      "--spool-accent": accent,
    }}>
      {/* outer rim (the plastic side of the spool) */}
      <div className="spool-rim" />
      {/* wound filament (color band) */}
      <div className="spool-wound" style={{
        width: woundR * 2, height: woundR * 2,
        animation: spinning ? "spool-spin 8s linear infinite" : "none",
      }}>
        <div className="spool-wound-inner" />
      </div>
      {/* core hole */}
      <div className="spool-hole" style={{ width: dims.hole * 2, height: dims.hole * 2 }} />
    </div>
  );
}

function formatDryTime(minutes) {
  const total = Number(minutes);
  if (!Number.isFinite(total) || total <= 0) return "--";
  const hours = Math.floor(total / 60);
  const mins = Math.round(total % 60);
  return hours > 0 ? `${hours}h ${String(mins).padStart(2, "0")}m` : `${mins}m`;
}

// ──────────────────────────────────────────────────────────────────────
// AMS 2 Pro — 4 slots, transparent lid, status strip
// ──────────────────────────────────────────────────────────────────────
function AMS2Pro({ unit, spools, onSlotClick, climate }) {
  // build slot array (0..3), find spool for each
  const slots = [0, 1, 2, 3].map(idx => {
    const s = spools.find(sp => sp.unit === unit.id && sp.slot === idx);
    return { idx, spool: s };
  });

  const loaded = slots.filter(s => s.spool).length;

  return (
    <div className="ams ams-2pro" data-unit={unit.id}>
      {/* Feed tubes — stick out the top */}
      <div className="ams-tubes">
        {[0,1,2,3].map(i => <div key={i} className="ams-tube" />)}
      </div>
      {/* Lid — translucent top */}
      <div className="ams-lid">
        <div className="ams-lid-tint" />
        <div className="ams-lid-shine" />
      </div>

      {/* Spool window — see-through, shows the 4 spools */}
      <div className="ams-window">
        {slots.map(({ idx, spool }) => (
          <button
            key={idx}
            className={`ams-bay ${spool ? "filled" : "empty"} ${spool?.active ? "active" : ""}`}
            onClick={() => onSlotClick(unit.id, idx, spool)}
            aria-label={`Slot ${idx + 1}`}
          >
            {spool ? (
              <Spool
                color={SPOOL_PALETTE[spool.color].hex}
                accent={SPOOL_PALETTE[spool.color].accent}
                remaining={spool.remaining}
                spinning={spool.active}
              />
            ) : (
              <div className="bay-empty">
                <div className="bay-empty-mount" />
                <div className="bay-empty-mount" />
              </div>
            )}
            <div className="bay-floor" />
          </button>
        ))}
      </div>

      {/* Chassis — bottom matte body with status display */}
      <div className="ams-chassis">
        <div className="ams-display">
          <div className="display-row">
            <span className="display-label">UNIT</span>
            <span className="display-value">{unit.label.split("·")[1].trim()}</span>
          </div>
          <div className="display-row">
            <span className="display-label">TEMP</span>
            <span className="display-value">{climate.temp.toFixed(1)}°</span>
          </div>
          <div className="display-row">
            <span className="display-label">RH</span>
            <span className="display-value">{climate.humidity}%</span>
          </div>
          <div className="display-row">
            <span className="display-label">LOAD</span>
            <span className="display-value">{loaded}/4</span>
          </div>
        </div>
        <div className="ams-badge">2 Pro</div>
      </div>

    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// AMS HT — single slot, taller, drying-focused, has a heater display
// ──────────────────────────────────────────────────────────────────────
function AMSHT({ unit, spools, onSlotClick, climate }) {
  const spool = spools.find(s => s.unit === unit.id && s.slot === 0);
  const isDrying = Boolean(climate.isDrying);

  return (
    <div className={`ams ams-ht ${isDrying ? "is-drying" : ""}`} data-unit={unit.id}>
      <div className="ams-tubes ht-tubes">
        <div className="ams-tube" />
      </div>
      <div className="ams-lid ht-lid">
        <div className="ams-lid-tint" />
        <div className="ams-lid-shine" />
      </div>

      <div className="ams-window ht-window">
        <button
          className={`ams-bay ht-bay ${spool ? "filled" : "empty"} ${spool?.active ? "active" : ""}`}
          onClick={() => onSlotClick(unit.id, 0, spool)}
          aria-label="HT slot"
        >
          {spool ? (
            <Spool
              color={SPOOL_PALETTE[spool.color].hex}
              accent={SPOOL_PALETTE[spool.color].accent}
              remaining={spool.remaining}
              size="ht"
              spinning={spool.active}
            />
          ) : (
            <div className="bay-empty">
              <div className="bay-empty-mount" />
              <div className="bay-empty-mount" />
            </div>
          )}
          <div className="bay-floor" />
        </button>
      </div>

      <div className="ams-chassis ht-chassis">
        {isDrying && (
          <div className="drying-status">
            <span className="drying-pulse" />
            <span>{climate.dryFilament || "Drying"}</span>
            <strong>{formatDryTime(climate.dryRemainingMinutes)}</strong>
          </div>
        )}
        <div className="ams-display ht-display">
          <div className="display-row">
            <span className="display-label">TEMP</span>
            <span className="display-value hot">{climate.temp.toFixed(0)}°C</span>
          </div>
          <div className="display-row">
            <span className="display-label">SET</span>
            <span className="display-value">{climate.drySetTemperatureC ? `${climate.drySetTemperatureC}°` : "--"}</span>
          </div>
          <div className="display-row">
            <span className="display-label">RH</span>
            <span className="display-value">{climate.humidity}%</span>
          </div>
        </div>
        <div className="ams-badge ht-badge">HT</div>
      </div>
    </div>
  );
}

window.Spool = Spool;
window.AMS2Pro = AMS2Pro;
window.AMSHT = AMSHT;
