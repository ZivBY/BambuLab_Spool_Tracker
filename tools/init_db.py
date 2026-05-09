from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS spools (
    id INTEGER PRIMARY KEY,
    tag_uid TEXT,
    tray_uuid TEXT,
    filament_id TEXT,
    material_type TEXT,
    sub_brand TEXT,
    color_hex TEXT,
    nominal_weight_g REAL,
    diameter_mm REAL,
    source TEXT NOT NULL DEFAULT 'bambu',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(tag_uid, tray_uuid)
);

CREATE TABLE IF NOT EXISTS ams_slot_observations (
    id INTEGER PRIMARY KEY,
    observed_at TEXT NOT NULL,
    printer_serial TEXT,
    ams_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    tag_uid TEXT,
    tray_uuid TEXT,
    material_type TEXT,
    sub_brand TEXT,
    color_hex TEXT,
    remain_percent REAL,
    total_len_mm REAL,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS current_ams_slots (
    ams_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    tag_uid TEXT,
    tray_uuid TEXT,
    material_type TEXT,
    sub_brand TEXT,
    color_hex TEXT,
    remain_percent REAL,
    nominal_weight_g REAL,
    estimated_remaining_g REAL,
    total_len_mm REAL,
    state INTEGER,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (ams_id, slot_id)
);

CREATE TABLE IF NOT EXISTS current_ams_units (
    ams_id TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    humidity INTEGER,
    humidity_raw INTEGER,
    temperature_c REAL,
    info TEXT,
    dry_time INTEGER,
    tray_count INTEGER,
    loaded_count INTEGER,
    raw_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS printer_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    observed_at TEXT NOT NULL,
    connection_state TEXT NOT NULL,
    gcode_state TEXT,
    mc_percent REAL,
    print_type TEXT,
    subtask_id TEXT,
    subtask_name TEXT,
    gcode_file TEXT,
    ams_rfid_status INTEGER,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS print_jobs (
    id INTEGER PRIMARY KEY,
    bambu_subtask_id TEXT,
    subtask_name TEXT,
    gcode_file TEXT,
    print_type TEXT,
    started_at TEXT,
    finished_at TEXT,
    outcome TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(bambu_subtask_id)
);

CREATE TABLE IF NOT EXISTS spool_usage_events (
    id INTEGER PRIMARY KEY,
    spool_id INTEGER REFERENCES spools(id),
    print_job_id INTEGER REFERENCES print_jobs(id),
    used_g REAL,
    used_mm REAL,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    note TEXT
);
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize the spool tracker database.")
    parser.add_argument("--db", type=Path, default=Path("data/spool_tracker.db"))
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as conn:
        conn.executescript(SCHEMA)

    print(f"Initialized database: {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
