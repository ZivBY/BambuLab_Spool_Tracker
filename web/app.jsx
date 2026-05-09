// Main dashboard application
const { useState, useEffect, useMemo } = React;

const LIVE_UNIT_IDS = {
  "0": "2pro-C",
  "1": "2pro-A",
  "128": "ht-B",
  "129": "ht-D",
};

function liveColorKey(slot) {
  return `live-${slot.ams_id}-${slot.slot_id}`;
}

function liveHex(slot) {
  if (!slot.color_hex || slot.color_hex.length < 6) return "#2b2721";
  return `#${slot.color_hex.slice(0, 6)}`;
}

function liveAccent(hex) {
  const lower = hex.toLowerCase();
  if (lower === "#ffffff") return "#c9c2b1";
  if (lower === "#000000") return "#0e0f14";
  return hex;
}

function liveColorName(hex) {
  const key = hex.replace("#", "").toUpperCase();
  const names = {
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
  return names[key] || key;
}

function livePercent(value) {
  if (value === null || value === undefined || Number(value) < 0) return 0;
  return Math.max(0, Math.min(1, Number(value) / 100));
}

function slotLoaded(slot) {
  return Boolean(slot.material_type || slot.tag_uid || slot.tray_uuid);
}

function unitIdForAms(amsId) {
  return LIVE_UNIT_IDS[String(amsId)];
}

function cleanDryValue(value) {
  if (value === null || value === undefined || value === "" || Number(value) < 0) return null;
  return value;
}

function adaptLiveData(data) {
  if (!data) return null;
  const climate = { ...window.CLIMATE };
  (data.ams_units || []).forEach((unit) => {
    const id = unitIdForAms(unit.ams_id);
    if (!id) return;
    climate[id] = {
      temp: Number(unit.temperature_c || 0),
      humidity: Number(unit.humidity_percent ?? unit.humidity_raw ?? unit.humidity ?? 0),
      humidityLevel: Number(unit.humidity_level ?? unit.humidity ?? 0),
      isDrying: Boolean(unit.is_drying),
      dryRemainingMinutes: cleanDryValue(unit.dry_remaining_minutes ?? unit.dry_time),
      drySetTemperatureC: cleanDryValue(unit.dry_set_temperature_c),
      dryDurationHours: cleanDryValue(unit.dry_duration_hours),
      dryFilament: unit.dry_filament || "",
    };
  });

  const spools = (data.slots || [])
    .filter(slotLoaded)
    .map((slot) => {
      const unit = unitIdForAms(slot.ams_id);
      const hex = liveHex(slot);
      const color = liveColorKey(slot);
      window.SPOOL_PALETTE[color] = {
        name: liveColorName(hex),
        hex,
        accent: liveAccent(hex),
      };
      return {
        id: slot.tag_uid || slot.tray_uuid || `${slot.ams_id}-${slot.slot_id}`,
        unit,
        slot: Number(slot.slot_id),
        material: slot.material_type || "Unknown",
        brand: slot.sub_brand || "Unlabeled",
        color,
        remaining: livePercent(slot.remain_percent),
        weight: Number(slot.nominal_weight_g || 1000),
        rfid: slot.tag_uid || slot.tray_uuid || "Manual",
        lastUsed: slot.observed_at ? new Date(slot.observed_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "just now",
        active: Number(slot.remain_percent) >= 0 && Number(slot.remain_percent) <= 10,
        raw: slot,
      };
    })
    .filter((spool) => spool.unit);

  const printer = data.printer || {};
  const job = {
    name: printer.subtask_name || printer.gcode_file || "No active print",
    spool: spools.find((spool) => spool.active)?.id || spools[0]?.id || "",
    layer: printer.gcode_state || "--",
    walls: 0,
    infill: 0,
    progress: Math.max(0, Math.min(0.999, Number(printer.mc_percent || 0) / 100)),
    eta: printer.gcode_state === "FINISH" ? "Done" : "--",
    state: printer.gcode_state || "--",
  };

  const activity = (data.recent_observations || []).slice(0, 12).map((item) => ({
    time: item.observed_at ? new Date(item.observed_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "--",
    unit: `${unitIdForAms(item.ams_id) || item.ams_id} · slot ${Number(item.slot_id) + 1}`,
    event: item.material_type || "Empty bay",
    detail: `${item.sub_brand || item.tag_uid || "No spool"} · ${item.remain_percent == null || Number(item.remain_percent) < 0 ? "unknown" : Math.round(Number(item.remain_percent)) + "%"}`,
  }));

  return { climate, spools, job, activity };
}

function Dashboard() {
  const [selected, setSelected] = useState(null);    // { unitId, slotIdx, spool }
  const [theme, setTheme] = useState("light");
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");
  const [job, setJob] = useState(window.CURRENT_JOB);
  const [spools, setSpools] = useState(window.SPOOLS);
  const [climate, setClimate] = useState(window.CLIMATE);
  const [activity, setActivity] = useState(window.ACTIVITY);

  // theme application
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    async function loadLive() {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        const mapped = adaptLiveData(await response.json());
        if (!mapped || cancelled) return;
        window.CLIMATE = mapped.climate;
        window.ACTIVITY = mapped.activity;
        setClimate(mapped.climate);
        setActivity(mapped.activity);
        setSpools(mapped.spools);
        setJob(mapped.job);
      } catch (error) {
        console.error("Failed to load live Bambu tracker data", error);
      }
    }
    loadLive();
    const id = setInterval(loadLive, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // very small visual tick while a print is active between telemetry refreshes
  useEffect(() => {
    if (job.state === "FINISH") return undefined;
    const id = setInterval(() => {
      setJob(j => ({ ...j, progress: Math.min(0.999, j.progress + 0.0002) }));
    }, 1500);
    return () => clearInterval(id);
  }, [job.state]);

  const handleSlotClick = (unitId, slotIdx, spool) => {
    setSelected({ unitId, slotIdx, spool });
  };

  const selectedUnit = selected ? UNITS.find(u => u.id === selected.unitId) : null;

  // inventory grouping — every spool is an inventory item; also include some "off-rack" spools
  const inventoryItems = useMemo(() => {
    const onRack = spools.map(s => ({
      ...s,
      location: UNITS.find(u => u.id === s.unit).label + " · slot " + (s.slot + 1),
    }));
    return onRack;
  }, [spools]);

  const materialFilters = useMemo(() => {
    const set = new Set(inventoryItems.map(i => i.material.split(" ")[0]));
    return ["All", ...Array.from(set)];
  }, [inventoryItems]);

  const filteredInventory = useMemo(() => {
    return inventoryItems.filter(item => {
      if (activeFilter !== "All" && !item.material.startsWith(activeFilter)) return false;
      if (search) {
        const q = search.toLowerCase();
        const hay = (item.rfid + " " + item.material + " " + item.brand + " " + SPOOL_PALETTE[item.color].name).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [inventoryItems, activeFilter, search]);

  return (
    <>
      <div className="app">
        <header className="topbar">
          <div className="brand">
            <div className="brand-mark">f</div>
            <div>
              <div className="brand-name">filament<em style={{ fontStyle: "italic" }}>·</em>desk</div>
              <div className="brand-sub">Workshop spool tracker</div>
            </div>
          </div>
          <div className="topbar-meta">
            <span className="live-pill"><span className="dot" />Live · 4 units online</span>
            <button className="chip" onClick={() => setTheme(t => t === "light" ? "dark" : "light")}>
              {theme === "light" ? "◑ Dark" : "◐ Light"}
            </button>
          </div>
        </header>

        <section className="hero">
          <div>
            <h1 className="hero-title">
              The bench, <em>at a glance.</em>
            </h1>
            <p className="hero-sub">
              Every spool, every drying cycle, every gram remaining — across the whole rack. Click any bay
              to inspect the spool sitting in it.
            </p>
          </div>
          <div className="hero-job">
            <div className="job-eyebrow">Currently printing</div>
            <div className="job-name">{job.name}</div>
            <div className="job-bar-track">
              <div className="job-bar-fill" style={{ width: (job.progress * 100).toFixed(1) + "%" }} />
            </div>
            <div className="job-grid">
              <div>
                <div className="job-stat-label">Progress</div>
                <div className="job-stat-value">{Math.round(job.progress * 100)}%</div>
              </div>
              <div>
                <div className="job-stat-label">ETA</div>
                <div className="job-stat-value">{job.eta}</div>
              </div>
              <div>
                <div className="job-stat-label">Layer</div>
                <div className="job-stat-value">{job.layer}</div>
              </div>
              <div>
                <div className="job-stat-label">State</div>
                <div className="job-stat-value">{job.state}</div>
              </div>
            </div>
          </div>
        </section>

        <div className="section-head">
          <div>
            <h2 className="section-title">The rack</h2>
            <div className="section-sub">Two-tier · 2 Pro paired with HT · click any bay</div>
          </div>
          <div className="legend">
            <span><span className="legend-dot" style={{ background: "var(--accent)" }} />Active feed</span>
            <span><span className="legend-dot" style={{ background: "var(--ink-3)" }} />Loaded</span>
            <span><span className="legend-dot" style={{ background: "var(--surface-3)", border: "1px solid var(--line)" }} />Empty</span>
          </div>
        </div>

        <div className="rack" data-screen-label="rack">
          <div className="rack-rows">
            {[0, 1].map(rowIdx => (
              <div className="rack-row" key={rowIdx}>
                <AMS2Pro
                  unit={UNITS.find(u => u.row === rowIdx && u.kind === "2pro")}
                  spools={spools}
                  onSlotClick={handleSlotClick}
                  climate={climate[UNITS.find(u => u.row === rowIdx && u.kind === "2pro").id]}
                />
                <AMSHT
                  unit={UNITS.find(u => u.row === rowIdx && u.kind === "ht")}
                  spools={spools}
                  onSlotClick={handleSlotClick}
                  climate={climate[UNITS.find(u => u.row === rowIdx && u.kind === "ht").id]}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="data-grid">
          <div className="card" data-screen-label="inventory">
            <div className="card-head">
              <div>
                <h3 className="card-title">Inventory</h3>
                <div className="card-sub">{filteredInventory.length} of {inventoryItems.length} spools</div>
              </div>
            </div>
            <div className="filters">
              <input
                className="search-input"
                placeholder="Search RFID, material, brand, color…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {materialFilters.map(f => (
                <button
                  key={f}
                  className={`chip ${activeFilter === f ? "on" : ""}`}
                  onClick={() => setActiveFilter(f)}
                >{f}</button>
              ))}
            </div>
            <div className="inventory-grid">
              {filteredInventory.map(item => {
                const palette = SPOOL_PALETTE[item.color];
                const pct = Math.round(item.remaining * 100);
                return (
                  <div key={item.id} className="inv-tile" onClick={() => {
                    // if it's on the rack, open the modal in-place
                    const onRack = spools.find(s => s.id === item.id);
                    if (onRack) {
                      const u = UNITS.find(u => u.id === onRack.unit);
                      setSelected({ unitId: u.id, slotIdx: onRack.slot, spool: onRack });
                    }
                  }}>
                    <div className="inv-swatch" style={{ background: `linear-gradient(135deg, ${palette.hex}, ${palette.accent})` }} />
                    <div>
                      <div className="inv-mat">{item.material}</div>
                      <div className="inv-meta">
                        <span>{palette.name}</span>
                        <span>{pct}%</span>
                      </div>
                    </div>
                    <div className="inv-bar">
                      <div className="inv-bar-fill" style={{ width: pct + "%", background: palette.hex }} />
                    </div>
                    <div className="inv-loc">{item.location}</div>
                  </div>
                );
              })}
              {filteredInventory.length === 0 && (
                <div style={{ gridColumn: "1/-1", padding: "32px", textAlign: "center", color: "var(--ink-3)" }}>
                  Nothing matches that filter.
                </div>
              )}
            </div>
          </div>

          <div className="card" data-screen-label="activity">
            <div className="card-head">
              <div>
                <h3 className="card-title">Activity</h3>
                <div className="card-sub">Recent scans, loads &amp; cycles</div>
              </div>
            </div>
            <div className="log">
              {activity.map((item, i) => (
                <div key={i} className="log-item">
                  <div className="log-time mono">{item.time}</div>
                  <div>
                    <div className="log-event">{item.event}</div>
                    <div className="log-detail">{item.detail}</div>
                    <div className="log-unit">{item.unit}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <SpoolModal
        open={!!selected}
        spool={selected?.spool}
        unit={selectedUnit}
        onClose={() => setSelected(null)}
      />

      <DashboardTweaks theme={theme} setTheme={setTheme} />
    </>
  );
}

function DashboardTweaks({ theme, setTheme }) {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    function handler(e) {
      if (e.data?.type === "__activate_edit_mode") setEnabled(true);
      if (e.data?.type === "__deactivate_edit_mode") setEnabled(false);
    }
    window.addEventListener("message", handler);
    window.parent.postMessage({ type: "__edit_mode_available" }, "*");
    return () => window.removeEventListener("message", handler);
  }, []);

  if (!enabled) return null;
  return (
    <TweaksPanel onClose={() => {
      setEnabled(false);
      window.parent.postMessage({ type: "__edit_mode_dismissed" }, "*");
    }}>
      <TweakSection title="Theme">
        <TweakRadio
          label="Mode"
          value={theme}
          onChange={setTheme}
          options={[
            { value: "light", label: "Light" },
            { value: "dark",  label: "Dark"  },
          ]}
        />
      </TweakSection>
    </TweaksPanel>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<Dashboard />);
