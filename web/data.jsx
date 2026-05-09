// Sample filament inventory data for the workshop dashboard.
// Original data shape — invented for this prototype.

const MATERIALS = ["PLA Basic", "PLA Matte", "PLA Silk", "PETG HF", "ABS", "ASA", "PA-CF", "TPU 95A", "PC", "Support W"];
const BRANDS = ["Polymaker", "Prusament", "eSun", "Hatchbox", "Overture", "Workshop Co.", "Sunlu"];

// Hand-curated palette for color realism. Each entry: { name, hex, accent }.
// `accent` is a darker rim color for the spool front view.
const SPOOL_PALETTE = {
  charcoal:   { name: "Charcoal",     hex: "#22232a", accent: "#0e0f14" },
  bone:       { name: "Bone White",   hex: "#f1ece1", accent: "#c9c2b1" },
  ember:      { name: "Ember",        hex: "#d8542b", accent: "#7a2c12" },
  marigold:   { name: "Marigold",     hex: "#e9a13b", accent: "#7e520f" },
  fern:       { name: "Fern",         hex: "#3f7a4a", accent: "#1d3c23" },
  teal:       { name: "Deep Teal",    hex: "#1f6c75", accent: "#0c3036" },
  cobalt:     { name: "Cobalt",       hex: "#2c4a9a", accent: "#11204b" },
  plum:       { name: "Plum",         hex: "#6b3a78", accent: "#321636" },
  sakura:     { name: "Sakura",       hex: "#e6a3b6", accent: "#a35569" },
  galaxy:     { name: "Galaxy Silk",  hex: "#2a2358", accent: "#0e0a26" },
  copper:     { name: "Copper Silk",  hex: "#a86a3d", accent: "#523018" },
  mint:       { name: "Mint",         hex: "#9ad3b7", accent: "#3f7762" },
  highviz:    { name: "Hi-Viz",       hex: "#d6e64c", accent: "#7e8c1c" },
  natural:    { name: "Natural",      hex: "#e7d9b8", accent: "#9c8a62" },
  void:       { name: "Void Black",   hex: "#0c0c10", accent: "#000000" },
};

// AMS units. Each has slots; HT has a single slot, 2 Pro has 4.
// Two rows mirrors the user's request: row 1 = (2 Pro + HT), row 2 = (2 Pro + HT).
const SPOOLS = [
  // Top 2 Pro — A
  { id: "A1", unit: "2pro-A", slot: 0, material: "PLA Basic",  brand: "Workshop Co.", color: "ember",     remaining: 0.84, weight: 1000, rfid: "RF-4587-01A0", lastUsed: "2 hours ago" },
  { id: "A2", unit: "2pro-A", slot: 1, material: "PLA Matte",  brand: "Polymaker",     color: "bone",      remaining: 0.42, weight: 1000, rfid: "RF-9F35-A220", lastUsed: "Yesterday" },
  { id: "A3", unit: "2pro-A", slot: 2, material: "PETG HF",    brand: "Prusament",     color: "fern",      remaining: 0.71, weight: 1000, rfid: "RF-CA5A-77B1", lastUsed: "3 days ago" },
  { id: "A4", unit: "2pro-A", slot: 3, material: "PLA Silk",   brand: "eSun",          color: "copper",    remaining: 0.18, weight: 1000, rfid: "RF-2210-3008", lastUsed: "Just now", active: true },

  // Top HT — B (single slot)
  { id: "B1", unit: "ht-B", slot: 0, material: "PA-CF",        brand: "Polymaker",     color: "charcoal",  remaining: 0.58, weight: 1000, rfid: "RF-77E1-9090", lastUsed: "Last week" },

  // Bottom 2 Pro — C
  { id: "C1", unit: "2pro-C", slot: 0, material: "PLA Basic",  brand: "Hatchbox",      color: "cobalt",    remaining: 0.93, weight: 1000, rfid: "RF-1129-AA42", lastUsed: "5 hours ago" },
  // C2 = empty
  { id: "C3", unit: "2pro-C", slot: 2, material: "PLA Silk",   brand: "Workshop Co.",  color: "galaxy",    remaining: 0.66, weight: 1000, rfid: "RF-8810-2244", lastUsed: "2 days ago" },
  { id: "C4", unit: "2pro-C", slot: 3, material: "TPU 95A",    brand: "Sunlu",         color: "highviz",   remaining: 0.31, weight: 1000, rfid: "RF-D031-5050", lastUsed: "1 hour ago" },

  // Bottom HT — D
  { id: "D1", unit: "ht-D", slot: 0, material: "ASA",          brand: "Overture",      color: "void",      remaining: 0.07, weight: 1000, rfid: "RF-0FF0-1111", lastUsed: "30 min ago" },
];

const UNITS = [
  { id: "2pro-A", kind: "2pro", label: "AMS 2 Pro · A", row: 0, col: 0 },
  { id: "ht-B",   kind: "ht",   label: "AMS HT · B",    row: 0, col: 1 },
  { id: "2pro-C", kind: "2pro", label: "AMS 2 Pro · C", row: 1, col: 0 },
  { id: "ht-D",   kind: "ht",   label: "AMS HT · D",    row: 1, col: 1 },
];

const CLIMATE = {
  "2pro-A": { temp: 24.6, humidity: 12 },
  "ht-B":   { temp: 62.0, humidity: 4  },
  "2pro-C": { temp: 25.1, humidity: 14 },
  "ht-D":   { temp: 58.4, humidity: 5  },
};

const ACTIVITY = [
  { time: "11:42", unit: "2pro-A · slot 4", event: "Print job started",   detail: "Painted brim pattern · 0.2mm" },
  { time: "11:38", unit: "ht-D",             event: "Drying cycle on",     detail: "Target 60°C · 4h remaining" },
  { time: "10:51", unit: "2pro-A · slot 2",  event: "Spool loaded",        detail: "PLA Matte · Bone White" },
  { time: "10:14", unit: "2pro-C · slot 2",  event: "RFID scan",           detail: "RF-8810-2244 verified" },
  { time: "09:33", unit: "2pro-C · slot 1",  event: "Remaining updated",   detail: "93% · 930g estimated" },
  { time: "08:02", unit: "ht-B",             event: "Climate stable",      detail: "62.0°C · 4% RH" },
  { time: "07:18", unit: "2pro-A · slot 1",  event: "Spool loaded",        detail: "PLA Basic · Ember" },
  { time: "Yesterday", unit: "2pro-C · slot 3", event: "Spool removed",   detail: "Manual eject" },
];

const CURRENT_JOB = {
  name: "Workshop Stool — Painted Brims",
  spool: "A4",
  layer: "0.20mm",
  walls: 3,
  infill: 18,
  progress: 0.62,
  eta: "1h 47m",
  state: "Printing",
};

window.SPOOL_PALETTE = SPOOL_PALETTE;
window.SPOOLS = SPOOLS;
window.UNITS = UNITS;
window.CLIMATE = CLIMATE;
window.ACTIVITY = ACTIVITY;
window.CURRENT_JOB = CURRENT_JOB;
window.MATERIALS = MATERIALS;
window.BRANDS = BRANDS;
