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
    "A02989": "Magenta",
    "0A2989": "Navy Blue",
    "8AB486": "Olive Green",
    "1F4EB3": "Blue",
    "002F7B": "Blue",
    "2E7D41": "Green",
    "7C5A33": "Brown",
    "A7C43A": "Lime",
    "382780": "Purple",
  };
  return names[key] || "Custom color";
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

function localTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatDryDuration(hours) {
  const value = Number(hours);
  if (!Number.isFinite(value) || value < 0) return "--";
  return `${value}h`;
}

function formatDryTime(minutes) {
  const total = Number(minutes);
  if (!Number.isFinite(total) || total <= 0) return "--";
  const hours = Math.floor(total / 60);
  const mins = Math.round(total % 60);
  return hours > 0 ? `${hours}h ${String(mins).padStart(2, "0")}m` : `${mins}m`;
}

function formatElapsedTime(minutes) {
  const total = Number(minutes);
  if (!Number.isFinite(total) || total < 0) return "--";
  if (total === 0) return "0m";
  return formatDryTime(total);
}

function formatRh(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${Math.round(Number(value))}%`;
}

function shortId(value) {
  if (!value) return "Manual";
  if (value.length <= 14) return value;
  return `${value.slice(0, 6)}...${value.slice(-4)}`;
}

function spoolOptionLabel(spool) {
  if (spool.inventory_source === "manual" || spool.manual_label) {
    return colorCodesToNames(spool.manual_label || spool.sub_brand || "Manual filament");
  }
  const colorName = spool.color_hex ? liveColorName(`#${spool.color_hex.slice(0, 6)}`) : "";
  return [spool.sub_brand, spool.material_type, colorName, shortId(spool.tag_uid || spool.tray_uuid)]
    .filter(Boolean)
    .join(" - ");
}

function inventoryOptionValue(spool) {
  return String(spool.inventory_id || spool.id || "");
}

function isManualInventoryEntry(spool) {
  return Boolean(spool && (spool.inventory_source === "manual" || spool.manual_label));
}

function manualInventoryLabel(spool) {
  return String(spool?.manual_label || spool?.sub_brand || "").trim();
}

function cleanColorCodes(value) {
  return String(value || "")
    .replace(/\s*-\s*#[0-9a-f]{6}\b/ig, "")
    .replace(/\s*#[0-9a-f]{6}\b/ig, "")
    .replace(/\s*-\s*[0-9a-f]{6}\.\.\.[0-9a-f]{4}\b/ig, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s*-\s*-\s*/g, " - ")
    .trim();
}

function colorCodesToNames(value) {
  return String(value || "")
    .replace(/#([0-9a-f]{6})\b/ig, match => liveColorName(match))
    .replace(/\s*-\s*[0-9a-f]{6}\.\.\.[0-9a-f]{4}\b/ig, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s*-\s*-\s*/g, " - ")
    .trim();
}

function extractColorHex(value) {
  const match = String(value || "").match(/#([0-9a-f]{6})\b/i);
  return match ? `#${match[1].toUpperCase()}` : "";
}

function filamentLabelParts(label) {
  return String(label || "")
    .split("|")
    .map(part => part.trim())
    .filter(Boolean);
}

function FilamentLabelList({ label, filaments = null, className = "" }) {
  const filamentItems = Array.isArray(filaments)
    ? filaments
        .filter(item => item.status !== "empty")
        .filter(item => item.status !== "unknown" || item.color_hex)
    : [];
  const parts = filamentItems.length
    ? filamentItems.map(item => ({
        text: item.filament_label || item.manual_filament_label || item.ams_filament_label || "Filament",
        hex: item.color_hex ? liveHex(item) : extractColorHex(item.filament_label),
      }))
    : filamentLabelParts(label).map(part => ({ text: part, hex: extractColorHex(part) }));
  const item = (part, index = 0) => {
    const hex = part.hex;
    return (
      <span className="filament-label-visual" key={`${part.text}-${index}`}>
        {hex && <span className="filament-color-dot" style={{ background: hex }} title={liveColorName(hex)} />}
        <span>{cleanColorCodes(part.text) || "Needs filament"}</span>
        {hex && <span className="filament-color-name">{liveColorName(hex)}</span>}
      </span>
    );
  };
  if (parts.length <= 1) return item(parts[0] || { text: "Needs filament", hex: "" });
  return (
    <ul className={`filament-label-list ${className}`.trim()}>
      {parts.map((part, index) => <li key={`${part.text}-${index}`}>{item(part, index)}</li>)}
    </ul>
  );
}

function dryingSourceLabel(source) {
  if (source === "rfid") return "RFID";
  if (source === "manual") return "Manual";
  return "Needs input";
}

function eventNeedsFilament(event) {
  if (event.needs_slot_input) return true;
  if (Array.isArray(event.filaments) && event.filaments.length) {
    return event.filaments.some(slot => slot.status === "unknown");
  }
  return !event.spool_id && !event.manual_filament_label;
}

function isAms2ProEvent(event) {
  return String(unitIdForAms(event.ams_id) || "").startsWith("2pro");
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
      dryFilament: colorCodesToNames(unit.drying_event_filament_label || unit.dry_filament || ""),
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

  const inventorySpools = (data.spools || []).map((spool) => {
    const source = spool.inventory_source || "rfid";
    const unit = spool.ams_id !== null && spool.ams_id !== undefined ? unitIdForAms(spool.ams_id) : null;
    const hex = spool.color_hex ? liveHex(spool) : "#8b8274";
    const color = source === "manual" ? `manual-${spool.id}` : liveColorKey({ ams_id: spool.ams_id || "stored", slot_id: spool.id });
    window.SPOOL_PALETTE[color] = {
      name: source === "manual" ? "Manual" : liveColorName(hex),
      hex,
      accent: liveAccent(hex),
    };
    return {
      id: spool.inventory_id || spool.id,
      unit,
      slot: spool.slot_id !== null && spool.slot_id !== undefined ? Number(spool.slot_id) : null,
      material: spool.material_type || (source === "manual" ? "Manual" : "Unknown"),
      brand: colorCodesToNames(spool.manual_label || spool.sub_brand || "Unlabeled"),
      color,
      remaining: livePercent(spool.remain_percent),
      remainingKnown: spool.remain_percent !== null && spool.remain_percent !== undefined && Number(spool.remain_percent) >= 0,
      weight: Number(spool.nominal_weight_g || 1000),
      rfid: spool.tag_uid || spool.tray_uuid || "Manual entry",
      lastUsed: spool.last_seen_at ? new Date(spool.last_seen_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "stored",
      isLoaded: Boolean(spool.is_loaded),
      source,
      raw: spool,
    };
  });

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

  return { climate, spools, inventorySpools, job, activity, dryingEvents: data.drying_events || [], rawSpools: data.spools || [] };
}

function DryingAssignmentForm({ event, spools, onAssign }) {
  const unknownSlots = (event.filaments || []).filter(slot => slot.status === "unknown");
  const initialEntries = unknownSlots.length
    ? unknownSlots.map(slot => ({
        slotId: slot.slot_id,
        spoolId: "",
        label: "",
        markedEmpty: false,
        amsLabel: slot.ams_filament_label || "",
      }))
    : [{ slotId: "0", spoolId: "", label: "", markedEmpty: false, amsLabel: "" }];
  const [spoolId, setSpoolId] = useState("");
  const [manualLabel, setManualLabel] = useState("");
  const [manualMarkedEmpty, setManualMarkedEmpty] = useState(false);
  const [filamentCount, setFilamentCount] = useState(initialEntries.length);
  const [filamentEntries, setFilamentEntries] = useState(initialEntries);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const is2Pro = isAms2ProEvent(event);

  function updateFilamentCount(value) {
    const count = Math.max(1, Math.min(4, Number(value) || 1));
    setFilamentCount(count);
    setFilamentEntries((entries) => {
      const next = entries.slice(0, count);
      while (next.length < count) next.push({ slotId: String(next.length), spoolId: "", label: "", markedEmpty: false, amsLabel: "" });
      return next;
    });
  }

  function updateFilamentEntry(index, patch) {
    setFilamentEntries((entries) => entries.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)));
  }

  function findKnownSpool(value) {
    return spools.find((item) => inventoryOptionValue(item) === String(value));
  }

  function entryKnownSpool(entry) {
    if (entry.spoolId) {
      return findKnownSpool(entry.spoolId);
    }
    return null;
  }

  function entryDisplayLabel(entry) {
    const spool = entryKnownSpool(entry);
    if (spool) return spoolOptionLabel(spool);
    return entry.label.trim();
  }

  function entryManualIdentityLabel(entry) {
    const spool = entryKnownSpool(entry);
    if (isManualInventoryEntry(spool)) {
      return manualInventoryLabel(spool);
    }
    return entry.label.trim();
  }

  async function submit(e) {
    e.preventDefault();
    const selectedKnown = findKnownSpool(spoolId);
    const selectedIsManual = isManualInventoryEntry(selectedKnown);
    const manualValue = is2Pro
      ? filamentEntries.filter(entry => !entry.markedEmpty).map(entryDisplayLabel).filter(Boolean).join(" | ")
      : manualMarkedEmpty ? "" : selectedIsManual ? manualInventoryLabel(selectedKnown) : manualLabel.trim();
    const slotAssignments = is2Pro
      ? (() => {
          const visibleSlotIds = new Set(filamentEntries.map(entry => String(entry.slotId)));
          const visibleAssignments = filamentEntries.map(entry => {
            const known = entryKnownSpool(entry);
            const knownIsManual = isManualInventoryEntry(known);
            const hasManualText = Boolean(entry.label.trim());
            const markedEmpty = Boolean(entry.markedEmpty || (!known && !hasManualText));
            return {
              slot_id: entry.slotId,
              spool_id: !markedEmpty && known && !knownIsManual ? known.id : null,
              manual_filament_label: markedEmpty ? "" : knownIsManual ? manualInventoryLabel(known) : entryManualIdentityLabel(entry),
              marked_empty: markedEmpty,
            };
          });
          const omittedAssignments = unknownSlots
            .filter(slot => !visibleSlotIds.has(String(slot.slot_id)))
            .map(slot => ({
              slot_id: slot.slot_id,
              spool_id: null,
              manual_filament_label: "",
              marked_empty: true,
            }));
          return [...visibleAssignments, ...omittedAssignments];
        })()
      : manualMarkedEmpty
        ? [{ slot_id: event.slot_id || "0", manual_filament_label: "", marked_empty: true }]
        : null;
    if (!spoolId && !manualValue && !(slotAssignments && slotAssignments.length)) return;
    setSaving(true);
    setError("");
    try {
      await onAssign(event.id, selectedIsManual ? null : spoolId, manualValue, slotAssignments);
    } catch (err) {
      setError(err.message || "Could not assign filament.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={`dry-assign-form ${error ? "has-error" : ""}`} onSubmit={submit} title={error}>
      {is2Pro ? (
        <>
          <label className="dry-count-control">
            <span>{unknownSlots.length ? "Unknown slots" : "Filaments"}</span>
            <select value={filamentCount} onChange={e => updateFilamentCount(e.target.value)} aria-label="Number of drying filaments">
              {[1, 2, 3, 4].map((count) => <option key={count} value={count}>{count}</option>)}
            </select>
          </label>
          <div className="dry-filament-fields">
            {filamentEntries.map((entry, index) => (
              <div className="dry-filament-row" key={index}>
                <div className="dry-slot-label">Slot {Number(entry.slotId) + 1}{entry.amsLabel ? ` · ${entry.amsLabel}` : ""}</div>
                <select
                  value={entry.spoolId}
                  onChange={e => updateFilamentEntry(index, { spoolId: e.target.value, markedEmpty: false })}
                  aria-label={`Known filament ${index + 1}`}
                  disabled={entry.markedEmpty}
                >
                  <option value="">Known filament...</option>
                  {spools.map(spool => (
                    <option key={inventoryOptionValue(spool)} value={inventoryOptionValue(spool)}>{spoolOptionLabel(spool)}</option>
                  ))}
                </select>
                <input
                  value={entry.label}
                  onChange={e => updateFilamentEntry(index, { label: e.target.value, markedEmpty: false })}
                  placeholder={`Filament ${index + 1}`}
                  aria-label={`Filament ${index + 1}`}
                  disabled={Boolean(entry.spoolId) || entry.markedEmpty}
                />
                <label className="dry-empty-control">
                  <input
                    type="checkbox"
                    checked={entry.markedEmpty}
                    onChange={e => updateFilamentEntry(index, { markedEmpty: e.target.checked, spoolId: e.target.checked ? "" : entry.spoolId, label: e.target.checked ? "" : entry.label })}
                  />
                  <span>Empty</span>
                </label>
              </div>
            ))}
          </div>
        </>
      ) : (
        <>
          <select value={spoolId} onChange={e => { setSpoolId(e.target.value); setManualMarkedEmpty(false); }} aria-label="Choose filament spool" disabled={manualMarkedEmpty}>
            <option value="">Choose known spool...</option>
            {spools.map(spool => (
              <option key={inventoryOptionValue(spool)} value={inventoryOptionValue(spool)}>{spoolOptionLabel(spool)}</option>
            ))}
          </select>
          <input
            value={manualLabel}
            onChange={e => { setManualLabel(e.target.value); setManualMarkedEmpty(false); }}
            placeholder="Or type filament"
            aria-label="Manual filament label"
            disabled={manualMarkedEmpty}
          />
          <label className="dry-empty-control">
            <input
              type="checkbox"
              checked={manualMarkedEmpty}
              onChange={e => {
                setManualMarkedEmpty(e.target.checked);
                if (e.target.checked) {
                  setSpoolId("");
                  setManualLabel("");
                }
              }}
            />
            <span>Empty</span>
          </label>
        </>
      )}
      <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? "Saving" : "Save"}</button>
    </form>
  );
}

function DryingEventList({ events, spools, onAssign }) {
  if (!events.length) return <div className="empty-note">No drying cycles recorded yet.</div>;
  return (
    <div className="drying-log">
      {events.slice(0, 10).map(event => {
        const active = !event.ended_at;
        const needsFilament = eventNeedsFilament(event);
        const temp = event.dry_temperature_c ?? "--";
        const label = event.filament_label || event.manual_filament_label || "Needs filament";
        return (
          <div key={event.id} className={`dry-event ${active ? "active" : ""} ${needsFilament ? "needs-input" : ""}`}>
            <div className="dry-event-main">
              <div className="dry-event-time mono">{localTime(event.started_at)}</div>
              <div>
                <div className="dry-event-title"><FilamentLabelList label={label} filaments={event.filaments} /></div>
                <div className="dry-event-detail">
                  {unitIdForAms(event.ams_id) || event.ams_id} · {event.dry_filament || "Manual"} · {temp}°C · {formatDryDuration(event.dry_duration_hours)}
                </div>
                <div className="dry-event-meta">
                  <span>{active ? "Drying now" : `Ended ${localTime(event.ended_at)}`}</span>
                  <span>{formatDryTime(event.last_remaining_minutes)} remaining</span>
                  <span>{dryingSourceLabel(event.attribution_source)}</span>
                </div>
              </div>
            </div>
            {needsFilament && <DryingAssignmentForm event={event} spools={spools} onAssign={onAssign} />}
          </div>
        );
      })}
    </div>
  );
}

function DryingHistory({ events }) {
  if (!events.length) return <div className="empty-note">No drying cycles recorded yet.</div>;
  return (
    <div className="dry-table-wrap">
      <table className="dry-table">
        <thead>
          <tr>
            <th>Started</th>
            <th>Ended</th>
            <th>Unit</th>
            <th>Filament</th>
            <th>Setting</th>
            <th>Start RH</th>
            <th>End RH</th>
            <th>Actual Time</th>
            <th>Time</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {events.map(event => {
            const active = !event.ended_at;
            const temp = event.dry_temperature_c ?? "--";
            const color = event.color_hex ? liveHex({ color_hex: event.color_hex }) : "";
            return (
              <tr key={event.id} className={active ? "is-active" : ""}>
                <td className="mono">{localTime(event.started_at)}</td>
                <td>{active ? "Active" : localTime(event.ended_at)}</td>
                <td>{unitIdForAms(event.ams_id) || event.ams_id}</td>
                <td>
                  <div className="dry-table-filament">
                    {color && <span className="dry-table-swatch" style={{ background: color }} />}
                    <FilamentLabelList label={event.filament_label || "Needs filament"} filaments={event.filaments} />
                  </div>
                </td>
                <td>{event.dry_filament || "Manual"} · {temp}°C · {formatDryDuration(event.dry_duration_hours)}</td>
                <td>{formatRh(event.start_humidity_percent)}</td>
                <td>{active ? "--" : formatRh(event.end_humidity_percent)}</td>
                <td>{formatElapsedTime(event.elapsed_duration_minutes)}</td>
                <td>{formatDryTime(event.last_remaining_minutes)}{active ? " left" : ""}</td>
                <td><span className={`source-pill ${event.attribution_source}`}>{dryingSourceLabel(event.attribution_source)}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function hexForInput(item) {
  const raw = item.raw?.color_hex || "";
  return raw ? `#${raw.slice(0, 6)}` : "";
}

function InventoryEditor({ items, onSave, onDelete }) {
  const [drafts, setDrafts] = useState({});
  const [savingId, setSavingId] = useState("");
  const [deletingId, setDeletingId] = useState("");
  const [message, setMessage] = useState("");

  function draftFor(item) {
    return drafts[item.id] || {
      label: item.raw?.manual_label || item.raw?.sub_brand || item.brand || "",
      material_type: item.source === "manual" ? "" : item.raw?.material_type || item.material || "",
      color_hex: item.source === "manual" ? "" : hexForInput(item),
      remain_percent: item.remainingKnown ? String(Math.round(item.remaining * 100)) : "",
    };
  }

  function updateDraft(item, patch) {
    setDrafts(current => ({
      ...current,
      [item.id]: { ...draftFor(item), ...patch },
    }));
  }

  async function saveItem(item) {
    const draft = draftFor(item);
    setSavingId(item.id);
    setMessage("");
    try {
      await onSave({
        inventory_id: item.id,
        label: draft.label,
        material_type: draft.material_type,
        color_hex: draft.color_hex,
        remain_percent: draft.remain_percent,
      });
      setDrafts(current => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      setMessage("Saved");
    } catch (err) {
      setMessage(err.message || "Could not save inventory item.");
    } finally {
      setSavingId("");
    }
  }

  async function deleteItem(item) {
    const confirmed = window.confirm(`Delete "${item.brand}" from inventory?`);
    if (!confirmed) return;
    setDeletingId(item.id);
    setMessage("");
    try {
      await onDelete({ inventory_id: item.id });
      setDrafts(current => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      setMessage("Deleted");
    } catch (err) {
      setMessage(err.message || "Could not delete inventory item.");
    } finally {
      setDeletingId("");
    }
  }

  if (!items.length) return <div className="empty-note">No inventory items match the current filters.</div>;

  return (
    <div className="inventory-editor">
      {message && <div className={`editor-message ${message === "Saved" || message === "Deleted" ? "is-ok" : "is-error"}`}>{message}</div>}
      {items.map(item => {
        const draft = draftFor(item);
        const palette = SPOOL_PALETTE[item.color];
        return (
          <div className="inventory-edit-row" key={item.id}>
            <div className="edit-swatch" style={{ background: item.source === "manual" ? palette.hex : draft.color_hex || palette.hex }} />
            <div className="edit-fields">
              <label>
                <span>{item.source === "manual" ? "Label" : "Brand / label"}</span>
                <input value={draft.label} onChange={e => updateDraft(item, { label: e.target.value })} />
              </label>
              <label>
                <span>Material</span>
                <input value={draft.material_type} onChange={e => updateDraft(item, { material_type: e.target.value })} disabled={item.source === "manual"} />
              </label>
              <label>
                <span>Color</span>
                <input type="color" value={draft.color_hex || "#8b8274"} onChange={e => updateDraft(item, { color_hex: e.target.value })} disabled={item.source === "manual"} />
              </label>
              <label>
                <span>Remaining %</span>
                <input type="number" min="0" max="100" value={draft.remain_percent} onChange={e => updateDraft(item, { remain_percent: e.target.value })} />
              </label>
            </div>
            <div className="edit-meta">
              <span className={`inv-source ${item.source}`}>{item.source === "manual" ? "Manual" : "RFID"}</span>
              <span>{item.location}</span>
              <button className="btn btn-primary" type="button" onClick={() => saveItem(item)} disabled={savingId === item.id}>
                {savingId === item.id ? "Saving" : "Save"}
              </button>
              <button className="btn btn-danger" type="button" onClick={() => deleteItem(item)} disabled={deletingId === item.id || savingId === item.id}>
                {deletingId === item.id ? "Deleting" : "Delete"}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Dashboard() {
  const [selected, setSelected] = useState(null);    // { unitId, slotIdx, spool }
  const [theme, setTheme] = useState("light");
  const [search, setSearch] = useState("");
  const [activeFilter, setActiveFilter] = useState("All");
  const [inventoryTab, setInventoryTab] = useState("overview");
  const [job, setJob] = useState(window.CURRENT_JOB);
  const [spools, setSpools] = useState(window.SPOOLS);
  const [climate, setClimate] = useState(window.CLIMATE);
  const [activity, setActivity] = useState(window.ACTIVITY);
  const [dryingEvents, setDryingEvents] = useState([]);
  const [rawSpools, setRawSpools] = useState([]);
  const [inventorySpools, setInventorySpools] = useState([]);

  // theme application
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    let loading = false;
    async function loadLive() {
      if (loading) return;
      loading = true;
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
        setDryingEvents(mapped.dryingEvents);
        setRawSpools(mapped.rawSpools);
        setInventorySpools(mapped.inventorySpools);
      } catch (error) {
        console.error("Failed to load live Bambu tracker data", error);
      } finally {
        loading = false;
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

  const assignDryingEvent = async (eventId, spoolId, manualFilamentLabel, slotAssignments = null) => {
    const response = await fetch("/api/drying-events/assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: eventId,
        spool_id: spoolId || null,
        manual_filament_label: manualFilamentLabel || "",
        slot_assignments: slotAssignments,
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Could not assign filament.");
    }
    const mapped = adaptLiveData(payload.data);
    if (!mapped) return;
    window.CLIMATE = mapped.climate;
    window.ACTIVITY = mapped.activity;
    setClimate(mapped.climate);
    setActivity(mapped.activity);
    setSpools(mapped.spools);
    setJob(mapped.job);
    setDryingEvents(mapped.dryingEvents);
    setRawSpools(mapped.rawSpools);
    setInventorySpools(mapped.inventorySpools);
  };

  const saveInventoryItem = async (item) => {
    const response = await fetch("/api/inventory/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Could not save inventory item.");
    }
    const mapped = adaptLiveData(payload.data);
    if (!mapped) return;
    window.CLIMATE = mapped.climate;
    window.ACTIVITY = mapped.activity;
    setClimate(mapped.climate);
    setActivity(mapped.activity);
    setSpools(mapped.spools);
    setJob(mapped.job);
    setDryingEvents(mapped.dryingEvents);
    setRawSpools(mapped.rawSpools);
    setInventorySpools(mapped.inventorySpools);
  };

  const deleteInventoryItem = async (item) => {
    const response = await fetch("/api/inventory/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Could not delete inventory item.");
    }
    const mapped = adaptLiveData(payload.data);
    if (!mapped) return;
    window.CLIMATE = mapped.climate;
    window.ACTIVITY = mapped.activity;
    setClimate(mapped.climate);
    setActivity(mapped.activity);
    setSpools(mapped.spools);
    setJob(mapped.job);
    setDryingEvents(mapped.dryingEvents);
    setRawSpools(mapped.rawSpools);
    setInventorySpools(mapped.inventorySpools);
  };

  // inventory grouping — every spool is an inventory item; also include some "off-rack" spools
  const inventoryItems = useMemo(() => {
    const onRack = inventorySpools.map(s => ({
      ...s,
      location: s.isLoaded && s.unit
        ? `${UNITS.find(u => u.id === s.unit)?.label || s.unit} · slot ${s.slot + 1}`
        : "Stored",
    }));
    return onRack;
  }, [inventorySpools]);

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
            <div className="tab-strip" role="tablist" aria-label="Inventory views">
              <button className={`tab-button ${inventoryTab === "overview" ? "is-active" : ""}`} type="button" onClick={() => setInventoryTab("overview")}>Overview</button>
              <button className={`tab-button ${inventoryTab === "edit" ? "is-active" : ""}`} type="button" onClick={() => setInventoryTab("edit")}>Edit</button>
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
            {inventoryTab === "overview" ? (
              <div className="inventory-grid">
                {filteredInventory.map(item => {
                  const palette = SPOOL_PALETTE[item.color];
                  const pct = Math.round(item.remaining * 100);
                  return (
                    <div key={item.id} className={`inv-tile ${item.isLoaded ? "is-loaded" : "is-stored"} ${item.source === "manual" ? "is-manual" : "is-rfid"}`} onClick={() => {
                      const onRack = spools.find(s => String(s.raw?.tag_uid || s.raw?.tray_uuid || s.id) === String(item.raw?.tag_uid || item.raw?.tray_uuid || item.id));
                      if (onRack) {
                        const u = UNITS.find(u => u.id === onRack.unit);
                        setSelected({ unitId: u.id, slotIdx: onRack.slot, spool: onRack });
                      }
                    }}>
                      <div className="inv-swatch" style={{ background: `linear-gradient(135deg, ${palette.hex}, ${palette.accent})` }} />
                      <div>
                        <div className="inv-mat">{item.material}</div>
                        <div className="inv-meta">
                          <span>{item.brand}</span>
                          <span>{item.remainingKnown ? `${pct}%` : "remaining unknown"}</span>
                        </div>
                      </div>
                      <div className="inv-bar">
                        <div className="inv-bar-fill" style={{ width: item.remainingKnown ? pct + "%" : "100%", background: item.remainingKnown ? palette.hex : "var(--line)" }} />
                      </div>
                      <div className="inv-loc">
                        <span>{item.location}</span>
                        <span className={`inv-source ${item.source}`}>{item.source === "manual" ? "Manual" : "RFID"}</span>
                      </div>
                    </div>
                  );
                })}
                {filteredInventory.length === 0 && (
                  <div style={{ gridColumn: "1/-1", padding: "32px", textAlign: "center", color: "var(--ink-3)" }}>
                    Nothing matches that filter.
                  </div>
                )}
              </div>
            ) : (
              <InventoryEditor items={filteredInventory} onSave={saveInventoryItem} onDelete={deleteInventoryItem} />
            )}
          </div>

          <div className="card" data-screen-label="activity">
            <div className="card-head">
              <div>
                <h3 className="card-title">Activity</h3>
                <div className="card-sub">Recent scans, loads &amp; cycles</div>
              </div>
            </div>
            <div className="log">
              <DryingEventList events={dryingEvents} spools={rawSpools} onAssign={assignDryingEvent} />
              <div className="activity-divider">Recent RFID observations</div>
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

          <div className="card wide-card" data-screen-label="drying-history">
            <div className="card-head">
              <div>
                <h3 className="card-title">Drying History</h3>
                <div className="card-sub">Cycle records with filament, setting, source and timing</div>
              </div>
            </div>
            <DryingHistory events={dryingEvents} />
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
