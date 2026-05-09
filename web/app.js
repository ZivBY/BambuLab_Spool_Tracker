const root = document.querySelector("#root");

let currentData = null;
let selectedSlot = null;
let theme = "light";

const COLOR_NAMES = {
  "000000": "Black",
  "FFFFFF": "White",
  "F72323": "Red",
  "C12E1F": "Red",
  "1F4EB3": "Blue",
  "2E7D41": "Green",
  "7C5A33": "Brown",
  "A7C43A": "Lime",
  "382780": "Purple",
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function bambuColor(hex) {
  if (!hex || hex.length < 6) return "#2b2721";
  return `#${hex.slice(0, 6)}`;
}

function colorName(hex) {
  if (!hex || hex.length < 6) return "Unknown";
  return COLOR_NAMES[hex.slice(0, 6).toUpperCase()] || `#${hex.slice(0, 6).toUpperCase()}`;
}

function colorAccent(hex) {
  const base = bambuColor(hex);
  if (base.toLowerCase() === "#ffffff") return "#c8c0ad";
  if (base.toLowerCase() === "#000000") return "#3b3a36";
  return base;
}

function percent(value) {
  if (value === null || value === undefined || Number(value) < 0) return 0;
  return Math.max(0, Math.min(100, Number(value)));
}

function percentText(value) {
  if (value === null || value === undefined || Number(value) < 0) return "Unknown";
  return `${Math.round(Number(value))}%`;
}

function gramsText(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "Unknown";
  return `${Math.round(Number(value))}g`;
}

function shortId(value) {
  if (!value) return "Manual";
  if (value.length <= 14) return value;
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function localTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function safeJson(value) {
  if (!value) return {};
  try {
    return JSON.parse(value);
  } catch {
    return {};
  }
}

function unitLabel(amsId) {
  if (Number(amsId) >= 128) return `AMS HT - ${Number(amsId) - 127}`;
  return `AMS 2 Pro - ${Number(amsId) + 1}`;
}

function unitShort(amsId) {
  if (Number(amsId) >= 128) return String.fromCharCode(65 + Number(amsId) - 128);
  return String.fromCharCode(65 + Number(amsId));
}

function mapSlot(slot) {
  const raw = safeJson(slot.raw_json);
  const loaded = Boolean(slot.material_type || slot.tag_uid || slot.tray_uuid);
  return {
    ...slot,
    raw,
    loaded,
    color: bambuColor(slot.color_hex),
    accent: colorAccent(slot.color_hex),
    colorName: colorName(slot.color_hex),
    remainingRatio: percent(slot.remain_percent) / 100,
    material: slot.material_type || "Empty",
    brand: slot.sub_brand || (loaded ? "Unlabeled filament" : "No spool detected"),
    rfid: slot.tag_uid || slot.tray_uuid || "",
    weight: slot.nominal_weight_g || 0,
  };
}

function buildRack(data) {
  const slots = (data.slots || []).map(mapSlot);
  const proUnits = [...new Set(slots.filter((slot) => Number(slot.ams_id) < 128).map((slot) => String(slot.ams_id)))]
    .sort((a, b) => {
      const loadedA = slots.filter((slot) => String(slot.ams_id) === a && slot.loaded).length;
      const loadedB = slots.filter((slot) => String(slot.ams_id) === b && slot.loaded).length;
      return loadedB - loadedA || Number(a) - Number(b);
    });
  const htUnits = [...new Set(slots.filter((slot) => Number(slot.ams_id) >= 128).map((slot) => String(slot.ams_id)))]
    .sort((a, b) => Number(a) - Number(b));

  return [0, 1].map((row) => ({
    proId: proUnits[row],
    htId: htUnits[row],
    proSlots: slots.filter((slot) => String(slot.ams_id) === proUnits[row]).sort((a, b) => Number(a.slot_id) - Number(b.slot_id)),
    htSlots: slots.filter((slot) => String(slot.ams_id) === htUnits[row]).sort((a, b) => Number(a.slot_id) - Number(b.slot_id)),
  })).filter((row) => row.proId || row.htId);
}

function climateFor(data, amsId) {
  return (data.ams_units || []).find((unit) => String(unit.ams_id) === String(amsId)) || {};
}

function climateRh(climate) {
  return climate.humidity_percent ?? climate.humidity_raw ?? climate.humidity ?? "--";
}

function dryValue(value) {
  return value === null || value === undefined || value === "" || Number(value) < 0 ? null : value;
}

function formatDryTime(minutes) {
  const total = Number(minutes);
  if (!Number.isFinite(total) || total <= 0) return "--";
  const hours = Math.floor(total / 60);
  const mins = Math.round(total % 60);
  return hours > 0 ? `${hours}h ${String(mins).padStart(2, "0")}m` : `${mins}m`;
}

function renderSpool(slot, size = "regular") {
  if (!slot.loaded) {
    return `
      <div class="bay-empty">
        <div class="bay-empty-mount"></div>
        <div class="bay-empty-mount"></div>
      </div>
    `;
  }

  const dims = size === "ht"
    ? { w: 110, h: 110, rim: 18, hole: 14 }
    : { w: 96, h: 96, rim: 16, hole: 12 };
  const innerR = dims.w / 2 - dims.rim;
  const coreR = dims.hole + 6;
  const woundR = coreR + (innerR - coreR) * slot.remainingRatio;
  const active = Number(slot.remain_percent) >= 0 && Number(slot.remain_percent) <= 10;

  return `
    <div class="spool" style="width:${dims.w}px;height:${dims.h}px;--spool-color:${slot.color};--spool-accent:${slot.accent}">
      <div class="spool-rim"></div>
      <div class="spool-wound" style="width:${woundR * 2}px;height:${woundR * 2}px;${active ? "animation:spool-spin 8s linear infinite" : ""}">
        <div class="spool-wound-inner"></div>
      </div>
      <div class="spool-hole" style="width:${dims.hole * 2}px;height:${dims.hole * 2}px"></div>
    </div>
  `;
}

function renderAMS2Pro(data, amsId, slots) {
  if (!amsId) return "";
  const climate = climateFor(data, amsId);
  const loaded = slots.filter((slot) => slot.loaded).length;
  const fourSlots = [0, 1, 2, 3].map((idx) => slots.find((slot) => Number(slot.slot_id) === idx) || {
    ams_id: amsId,
    slot_id: String(idx),
    loaded: false,
    material: "Empty",
    brand: "No spool detected",
    color: "#2b2721",
    accent: "#2b2721",
    remainingRatio: 0,
  });

  return `
    <div class="ams ams-2pro" data-unit="${esc(amsId)}">
      <div class="ams-tubes">${[0, 1, 2, 3].map(() => '<div class="ams-tube"></div>').join("")}</div>
      <div class="ams-lid"><div class="ams-lid-tint"></div><div class="ams-lid-shine"></div></div>
      <div class="ams-window">
        ${fourSlots.map((slot) => `
          <button class="ams-bay ${slot.loaded ? "filled" : "empty"} ${percent(slot.remain_percent) <= 10 && slot.loaded ? "active" : ""}" data-ams="${esc(slot.ams_id)}" data-slot="${esc(slot.slot_id)}" aria-label="Slot ${Number(slot.slot_id) + 1}">
            ${renderSpool(slot)}
            <div class="bay-floor"></div>
          </button>
        `).join("")}
      </div>
      <div class="ams-chassis">
        <div class="ams-display">
          <div class="display-row"><span class="display-label">UNIT</span><span class="display-value">${esc(unitShort(amsId))}</span></div>
          <div class="display-row"><span class="display-label">TEMP</span><span class="display-value">${Number(climate.temperature_c || 0).toFixed(1)}&deg;</span></div>
          <div class="display-row"><span class="display-label">RH</span><span class="display-value">${climateRh(climate)}%</span></div>
          <div class="display-row"><span class="display-label">LOAD</span><span class="display-value">${loaded}/4</span></div>
        </div>
        <div class="ams-badge">2 Pro</div>
      </div>
    </div>
  `;
}

function renderAMSHT(data, amsId, slots) {
  if (!amsId) return "";
  const climate = climateFor(data, amsId);
  const isDrying = Boolean(climate.is_drying || Number(climate.dry_time) > 0);
  const setTemp = dryValue(climate.dry_set_temperature_c);
  const dryFilament = climate.dry_filament || "Drying";
  const remaining = dryValue(climate.dry_remaining_minutes ?? climate.dry_time);
  const slot = slots[0] || {
    ams_id: amsId,
    slot_id: "0",
    loaded: false,
    material: "Empty",
    brand: "No spool detected",
    color: "#2b2721",
    accent: "#2b2721",
    remainingRatio: 0,
  };

  return `
    <div class="ams ams-ht ${isDrying ? "is-drying" : ""}" data-unit="${esc(amsId)}">
      <div class="ams-tubes ht-tubes"><div class="ams-tube"></div></div>
      <div class="ams-lid ht-lid"><div class="ams-lid-tint"></div><div class="ams-lid-shine"></div></div>
      <div class="ams-window ht-window">
        <button class="ams-bay ht-bay ${slot.loaded ? "filled" : "empty"}" data-ams="${esc(slot.ams_id)}" data-slot="${esc(slot.slot_id)}" aria-label="HT slot">
          ${renderSpool(slot, "ht")}
          <div class="bay-floor"></div>
        </button>
      </div>
      <div class="ams-chassis ht-chassis">
        ${isDrying ? `
          <div class="drying-status">
            <span class="drying-pulse"></span>
            <span>${esc(dryFilament)}</span>
            <strong>${esc(formatDryTime(remaining))}</strong>
          </div>
        ` : ""}
        <div class="ams-display ht-display">
          <div class="display-row"><span class="display-label">TEMP</span><span class="display-value hot">${Number(climate.temperature_c || 0).toFixed(0)}&deg;C</span></div>
          <div class="display-row"><span class="display-label">SET</span><span class="display-value">${setTemp ? `${esc(setTemp)}&deg;` : "--"}</span></div>
          <div class="display-row"><span class="display-label">RH</span><span class="display-value">${climateRh(climate)}%</span></div>
        </div>
        <div class="ams-badge ht-badge">HT</div>
      </div>
    </div>
  `;
}

function renderInventory(data) {
  const slots = (data.slots || []).map(mapSlot).filter((slot) => slot.loaded);
  if (!slots.length) {
    return '<div style="grid-column:1/-1;padding:32px;text-align:center;color:var(--ink-3)">No RFID spools detected yet.</div>';
  }
  return slots.map((slot) => {
    const pct = Math.round(percent(slot.remain_percent));
    return `
      <div class="inv-tile" data-ams="${esc(slot.ams_id)}" data-slot="${esc(slot.slot_id)}">
        <div class="inv-swatch" style="background:linear-gradient(135deg, ${slot.color}, ${slot.accent})"></div>
        <div>
          <div class="inv-mat">${esc(slot.material)}</div>
          <div class="inv-meta"><span>${esc(slot.colorName)}</span><span>${percentText(slot.remain_percent)}</span></div>
        </div>
        <div class="inv-bar"><div class="inv-bar-fill" style="width:${pct}%;background:${slot.color}"></div></div>
        <div class="inv-loc">${esc(unitLabel(slot.ams_id))} - slot ${Number(slot.slot_id) + 1}</div>
      </div>
    `;
  }).join("");
}

function renderActivity(data) {
  const events = data.recent_observations || [];
  return events.slice(0, 12).map((event) => `
    <div class="log-item">
      <div class="log-time mono">${esc(localTime(event.observed_at))}</div>
      <div>
        <div class="log-event">${esc(event.material_type || "Empty bay")}</div>
        <div class="log-detail">${esc(event.sub_brand || shortId(event.tag_uid))} - ${esc(percentText(event.remain_percent))}</div>
        <div class="log-unit">${esc(unitLabel(event.ams_id))} - slot ${Number(event.slot_id) + 1}</div>
      </div>
    </div>
  `).join("");
}

function renderModal() {
  if (!selectedSlot) return "";
  const slot = selectedSlot;
  if (!slot.loaded) {
    return `
      <div class="modal-backdrop" data-close-modal>
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" data-close-modal aria-label="Close">&times;</button>
          <div class="modal-empty">
            <div class="modal-empty-icon">O</div>
            <h2>Empty bay</h2>
            <p class="muted">No spool detected in ${esc(unitLabel(slot.ams_id))}.</p>
            <button class="btn btn-primary" data-close-modal>Close</button>
          </div>
        </div>
      </div>
    `;
  }

  const raw = slot.raw || {};
  const pct = Math.round(percent(slot.remain_percent));
  const remainingG = slot.estimated_remaining_g ?? (slot.weight ? slot.weight * slot.remainingRatio : null);
  return `
    <div class="modal-backdrop" data-close-modal>
      <div class="modal" role="dialog" aria-modal="true">
        <button class="modal-close" data-close-modal aria-label="Close">&times;</button>
        <div class="modal-hero" style="background:radial-gradient(circle at 30% 30%, ${slot.color}33, transparent 60%), var(--surface-2)">
          <div class="modal-hero-spool">${renderSpool(slot, "ht")}</div>
          <div class="modal-hero-meta">
            <div class="modal-eyebrow">${esc(unitLabel(slot.ams_id))} - Slot ${Number(slot.slot_id) + 1}</div>
            <h2 class="modal-title">${esc(slot.material)}</h2>
            <div class="modal-sub"><span class="dot" style="background:${slot.color}"></span>${esc(slot.colorName)} - ${esc(slot.brand)}</div>
          </div>
        </div>
        <div class="modal-body">
          <div class="stat-grid">
            <div class="stat">
              <div class="stat-label">Remaining</div>
              <div class="stat-value">${pct}<span>%</span></div>
              <div class="bar"><div class="bar-fill" style="width:${pct}%;background:${slot.color}"></div></div>
            </div>
            <div class="stat">
              <div class="stat-label">Estimate</div>
              <div class="stat-value">${esc(gramsText(remainingG))}</div>
              <div class="muted small">of ${esc(gramsText(slot.nominal_weight_g))} nominal</div>
            </div>
            <div class="stat">
              <div class="stat-label">RFID</div>
              <div class="stat-value mono">${esc(slot.rfid || "Manual")}</div>
              <div class="muted small">tray ${esc(raw.tray_id_name || "unknown")}</div>
            </div>
            <div class="stat">
              <div class="stat-label">Nozzle</div>
              <div class="stat-value mono">${esc(raw.nozzle_temp_min || "--")} - ${esc(raw.nozzle_temp_max || "--")} C</div>
              <div class="muted small">diameter ${esc(raw.tray_diameter || "--")} mm</div>
            </div>
          </div>
          <div class="modal-actions">
            <button class="btn">Mark spent</button>
            <button class="btn">Recalibrate weight</button>
            <button class="btn btn-primary">Set as active</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function render(data) {
  currentData = data;
  document.documentElement.dataset.theme = theme;
  const printer = data.printer || {};
  const progressValue = percent(printer.mc_percent);
  const rows = buildRack(data);
  const onlineUnits = data.ams_units?.length || 0;
  const loaded = (data.slots || []).filter((slot) => slot.material_type || slot.tag_uid || slot.tray_uuid).length;

  root.innerHTML = `
    <div class="app">
      <header class="topbar">
        <div class="brand">
          <div class="brand-mark">f</div>
          <div>
            <div class="brand-name">filament<em style="font-style:italic">&middot;</em>desk</div>
            <div class="brand-sub">Workshop spool tracker</div>
          </div>
        </div>
        <div class="topbar-meta">
          <span class="live-pill"><span class="dot"></span>Live &middot; ${onlineUnits} units online</span>
          <button class="chip" id="themeToggle">${theme === "light" ? "Dark" : "Light"}</button>
        </div>
      </header>

      <section class="hero">
        <div>
          <h1 class="hero-title">The bench, <em>at a glance.</em></h1>
          <p class="hero-sub">Every spool, every drying cycle, every gram remaining &mdash; across the whole rack. Click any bay to inspect the spool sitting in it.</p>
        </div>
        <div class="hero-job">
          <div class="job-eyebrow">Currently printing</div>
          <div class="job-name">${esc(printer.subtask_name || printer.gcode_file || "No active print")}</div>
          <div class="job-bar-track"><div class="job-bar-fill" style="width:${progressValue}%"></div></div>
          <div class="job-grid">
            <div><div class="job-stat-label">Progress</div><div class="job-stat-value">${Math.round(progressValue)}%</div></div>
            <div><div class="job-stat-label">Spools</div><div class="job-stat-value">${loaded}</div></div>
            <div><div class="job-stat-label">Units</div><div class="job-stat-value">${onlineUnits}</div></div>
            <div><div class="job-stat-label">State</div><div class="job-stat-value">${esc(printer.gcode_state || "--")}</div></div>
          </div>
        </div>
      </section>

      <div class="section-head">
        <div>
          <h2 class="section-title">The rack</h2>
          <div class="section-sub">Two-tier &middot; 2 Pro paired with HT &middot; click any bay</div>
        </div>
        <div class="legend">
          <span><span class="legend-dot" style="background:var(--accent)"></span>Low / active</span>
          <span><span class="legend-dot" style="background:var(--ink-3)"></span>Loaded</span>
          <span><span class="legend-dot" style="background:var(--surface-3);border:1px solid var(--line)"></span>Empty</span>
        </div>
      </div>

      <div class="rack" data-screen-label="rack">
        <div class="rack-rows">
          ${rows.map((row) => `
            <div class="rack-row">
              ${renderAMS2Pro(data, row.proId, row.proSlots)}
              ${renderAMSHT(data, row.htId, row.htSlots)}
            </div>
          `).join("")}
        </div>
      </div>

      <div class="data-grid">
        <div class="card" data-screen-label="inventory">
          <div class="card-head">
            <div>
              <h3 class="card-title">Inventory</h3>
              <div class="card-sub">${loaded} loaded spools</div>
            </div>
          </div>
          <div class="inventory-grid">${renderInventory(data)}</div>
        </div>
        <div class="card" data-screen-label="activity">
          <div class="card-head">
            <div>
              <h3 class="card-title">Activity</h3>
              <div class="card-sub">Recent scans, loads and cycles</div>
            </div>
          </div>
          <div class="log">${renderActivity(data)}</div>
        </div>
      </div>
    </div>
    ${renderModal()}
  `;
}

async function refresh() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    render(await response.json());
  } catch (error) {
    root.innerHTML = `<div class="app"><p class="hero-sub">Tracker API is not responding.</p></div>`;
  }
}

root.addEventListener("click", (event) => {
  const themeButton = event.target.closest("#themeToggle");
  if (themeButton) {
    theme = theme === "light" ? "dark" : "light";
    render(currentData);
    return;
  }

  const closeButton = event.target.closest(".modal-close, .modal-empty .btn");
  const clickedBackdrop = event.target.classList?.contains("modal-backdrop");
  if (closeButton || clickedBackdrop) {
    selectedSlot = null;
    render(currentData);
    return;
  }

  const bay = event.target.closest("[data-ams][data-slot]");
  if (bay && currentData) {
    const amsId = bay.dataset.ams;
    const slotId = bay.dataset.slot;
    selectedSlot = (currentData.slots || []).map(mapSlot).find((slot) => String(slot.ams_id) === amsId && String(slot.slot_id) === slotId) || {
      ams_id: amsId,
      slot_id: slotId,
      loaded: false,
    };
    render(currentData);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && selectedSlot) {
    selectedSlot = null;
    render(currentData);
  }
});

refresh();
setInterval(refresh, 5000);
