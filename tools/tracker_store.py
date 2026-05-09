from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_uid(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or set(text) == {"0"}:
        return None
    return text


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    schema_path = Path(__file__).with_name("init_db.py")
    namespace: dict[str, Any] = {}
    exec(schema_path.read_text(encoding="utf-8"), namespace)
    conn.executescript(namespace["SCHEMA"])


def upsert_spool(conn: sqlite3.Connection, observed_at: str, tray: dict[str, Any]) -> int | None:
    tag_uid = normalize_uid(tray.get("tag_uid"))
    tray_uuid = normalize_uid(tray.get("tray_uuid"))
    if not tag_uid and not tray_uuid:
        return None

    conn.execute(
        """
        INSERT INTO spools (
            tag_uid, tray_uuid, filament_id, material_type, sub_brand, color_hex,
            nominal_weight_g, diameter_mm, first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tag_uid, tray_uuid) DO UPDATE SET
            filament_id = excluded.filament_id,
            material_type = excluded.material_type,
            sub_brand = excluded.sub_brand,
            color_hex = excluded.color_hex,
            nominal_weight_g = excluded.nominal_weight_g,
            diameter_mm = excluded.diameter_mm,
            last_seen_at = excluded.last_seen_at
        """,
        (
            tag_uid,
            tray_uuid,
            tray.get("tray_info_idx"),
            tray.get("tray_type"),
            tray.get("tray_sub_brands"),
            tray.get("tray_color"),
            as_float(tray.get("tray_weight")),
            as_float(tray.get("tray_diameter")),
            observed_at,
            observed_at,
        ),
    )
    row = conn.execute(
        "SELECT id FROM spools WHERE tag_uid IS ? AND tray_uuid IS ?",
        (tag_uid, tray_uuid),
    ).fetchone()
    return int(row["id"]) if row else None


def record_status(conn: sqlite3.Connection, observed_at: str, status: dict[str, Any], connection_state: str = "connected") -> None:
    conn.execute(
        """
        INSERT INTO printer_status (
            id, observed_at, connection_state, gcode_state, mc_percent, print_type,
            subtask_id, subtask_name, gcode_file, ams_rfid_status, raw_json
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            observed_at = excluded.observed_at,
            connection_state = excluded.connection_state,
            gcode_state = excluded.gcode_state,
            mc_percent = excluded.mc_percent,
            print_type = excluded.print_type,
            subtask_id = excluded.subtask_id,
            subtask_name = excluded.subtask_name,
            gcode_file = excluded.gcode_file,
            ams_rfid_status = excluded.ams_rfid_status,
            raw_json = excluded.raw_json
        """,
        (
            observed_at,
            connection_state,
            status.get("gcode_state"),
            as_float(status.get("mc_percent")),
            status.get("print_type"),
            status.get("subtask_id"),
            status.get("subtask_name"),
            status.get("gcode_file"),
            as_int(status.get("ams_rfid_status")),
            json.dumps(status, sort_keys=True),
        ),
    )


def record_ams_units(conn: sqlite3.Connection, observed_at: str, status: dict[str, Any]) -> int:
    updated = 0
    for ams in status.get("ams", {}).get("ams", []):
        ams_id = str(ams.get("id", ""))
        if not ams_id:
            continue
        trays = ams.get("tray", [])
        loaded_count = sum(
            1
            for tray in trays
            if tray.get("tray_type") or normalize_uid(tray.get("tag_uid")) or normalize_uid(tray.get("tray_uuid"))
        )
        conn.execute(
            """
            INSERT INTO current_ams_units (
                ams_id, observed_at, humidity, humidity_raw, temperature_c,
                info, dry_time, tray_count, loaded_count, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ams_id) DO UPDATE SET
                observed_at = excluded.observed_at,
                humidity = excluded.humidity,
                humidity_raw = excluded.humidity_raw,
                temperature_c = excluded.temperature_c,
                info = excluded.info,
                dry_time = excluded.dry_time,
                tray_count = excluded.tray_count,
                loaded_count = excluded.loaded_count,
                raw_json = excluded.raw_json
            """,
            (
                ams_id,
                observed_at,
                as_int(ams.get("humidity")),
                as_int(ams.get("humidity_raw")),
                as_float(ams.get("temp")),
                ams.get("info"),
                as_int(ams.get("dry_time")),
                len(trays),
                loaded_count,
                json.dumps(ams, sort_keys=True),
            ),
        )
        updated += 1
    return updated


def record_ams_slots(conn: sqlite3.Connection, observed_at: str, printer_serial: str, status: dict[str, Any]) -> tuple[int, int]:
    observations = 0
    identified = 0

    for ams in status.get("ams", {}).get("ams", []):
        ams_id = str(ams.get("id", ""))
        if not ams_id:
            continue
        for tray in ams.get("tray", []):
            slot_id = str(tray.get("id", ""))
            if not slot_id:
                continue

            spool_id = upsert_spool(conn, observed_at, tray)
            if spool_id:
                identified += 1

            tag_uid = normalize_uid(tray.get("tag_uid"))
            tray_uuid = normalize_uid(tray.get("tray_uuid"))
            remain_percent = as_float(tray.get("remain"))
            nominal_weight_g = as_float(tray.get("tray_weight"))
            estimated_remaining_g = None
            if remain_percent is not None and nominal_weight_g and remain_percent >= 0:
                estimated_remaining_g = nominal_weight_g * remain_percent / 100

            row = (
                observed_at,
                printer_serial,
                ams_id,
                slot_id,
                tag_uid,
                tray_uuid,
                tray.get("tray_type"),
                tray.get("tray_sub_brands"),
                tray.get("tray_color"),
                remain_percent,
                as_float(tray.get("total_len")),
                json.dumps(tray, sort_keys=True),
            )
            conn.execute(
                """
                INSERT INTO ams_slot_observations (
                    observed_at, printer_serial, ams_id, slot_id, tag_uid, tray_uuid,
                    material_type, sub_brand, color_hex, remain_percent,
                    total_len_mm, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            conn.execute(
                """
                INSERT INTO current_ams_slots (
                    ams_id, slot_id, observed_at, tag_uid, tray_uuid, material_type,
                    sub_brand, color_hex, remain_percent, nominal_weight_g,
                    estimated_remaining_g, total_len_mm, state, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ams_id, slot_id) DO UPDATE SET
                    observed_at = excluded.observed_at,
                    tag_uid = excluded.tag_uid,
                    tray_uuid = excluded.tray_uuid,
                    material_type = excluded.material_type,
                    sub_brand = excluded.sub_brand,
                    color_hex = excluded.color_hex,
                    remain_percent = excluded.remain_percent,
                    nominal_weight_g = excluded.nominal_weight_g,
                    estimated_remaining_g = excluded.estimated_remaining_g,
                    total_len_mm = excluded.total_len_mm,
                    state = excluded.state,
                    raw_json = excluded.raw_json
                """,
                (
                    ams_id,
                    slot_id,
                    observed_at,
                    tag_uid,
                    tray_uuid,
                    tray.get("tray_type"),
                    tray.get("tray_sub_brands"),
                    tray.get("tray_color"),
                    remain_percent,
                    nominal_weight_g,
                    estimated_remaining_g,
                    as_float(tray.get("total_len")),
                    as_int(tray.get("state")),
                    json.dumps(tray, sort_keys=True),
                ),
            )
            observations += 1

    return observations, identified


def record_printer_message(conn: sqlite3.Connection, observed_at: str, printer_serial: str, payload: dict[str, Any]) -> tuple[int, int]:
    status = payload.get("print")
    if not isinstance(status, dict):
        return 0, 0
    record_status(conn, observed_at, status)
    record_ams_units(conn, observed_at, status)
    return record_ams_slots(conn, observed_at, printer_serial, status)


def rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dashboard_snapshot(db_path: Path) -> dict[str, Any]:
    with connect_db(db_path) as conn:
        init_schema(conn)
        status_row = conn.execute(
            """
            SELECT id, observed_at, connection_state, gcode_state, mc_percent,
                   print_type, subtask_id, subtask_name, gcode_file, ams_rfid_status
            FROM printer_status
            WHERE id = 1
            """
        ).fetchone()
        slots = rows_as_dicts(
            conn.execute(
                """
                SELECT ams_id, slot_id, observed_at, tag_uid, tray_uuid,
                       material_type, sub_brand, color_hex, remain_percent,
                       nominal_weight_g, estimated_remaining_g, total_len_mm, state,
                       raw_json
                FROM current_ams_slots
                ORDER BY CAST(ams_id AS INTEGER), CAST(slot_id AS INTEGER)
                """
            ).fetchall()
        )
        ams_units = rows_as_dicts(
            conn.execute(
                """
                SELECT ams_id, observed_at, humidity, humidity_raw, temperature_c,
                       info, dry_time, tray_count, loaded_count, raw_json
                FROM current_ams_units
                ORDER BY CAST(ams_id AS INTEGER)
                """
            ).fetchall()
        )
        for unit in ams_units:
            # Bambu reports `humidity` as a coarse 1-5 chamber level. The
            # machine UI's RH readout is represented by `humidity_raw`.
            unit["humidity_level"] = unit.get("humidity")
            unit["humidity_percent"] = unit.get("humidity_raw") if unit.get("humidity_raw") is not None else unit.get("humidity")
            raw = json.loads(unit.get("raw_json") or "{}")
            dry_setting = raw.get("dry_setting") or {}
            dry_time = unit.get("dry_time")
            unit["is_drying"] = bool(dry_time and dry_time > 0)
            unit["dry_remaining_minutes"] = dry_time
            unit["dry_set_temperature_c"] = dry_setting.get("dry_temperature")
            unit["dry_duration_hours"] = dry_setting.get("dry_duration")
            unit["dry_filament"] = dry_setting.get("dry_filament")
            unit["dry_stop_reasons"] = raw.get("dry_sf_reason") or []
        spools = rows_as_dicts(
            conn.execute(
                """
                SELECT s.*, latest.remain_percent, latest.estimated_remaining_g,
                       latest.ams_id, latest.slot_id
                FROM spools s
                LEFT JOIN (
                    SELECT tag_uid, tray_uuid, remain_percent, estimated_remaining_g, ams_id, slot_id
                    FROM current_ams_slots
                    WHERE tag_uid IS NOT NULL OR tray_uuid IS NOT NULL
                ) latest
                  ON latest.tag_uid IS s.tag_uid AND latest.tray_uuid IS s.tray_uuid
                ORDER BY s.last_seen_at DESC
                """
            ).fetchall()
        )
        recent = rows_as_dicts(
            conn.execute(
                """
                SELECT observed_at, ams_id, slot_id, tag_uid, material_type,
                       sub_brand, color_hex, remain_percent
                FROM ams_slot_observations
                ORDER BY id DESC
                LIMIT 30
                """
            ).fetchall()
        )

    return {
        "printer": dict(status_row) if status_row else None,
        "ams_units": ams_units,
        "slots": slots,
        "spools": spools,
        "recent_observations": recent,
    }
