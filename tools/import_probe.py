from __future__ import annotations

import argparse
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


def first_status(capture: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    for message in capture.get("messages", []):
        payload = message.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("print"), dict):
            return message.get("received_at", capture["captured_at"]), payload["print"]
    raise RuntimeError("No printer status payload found in capture.")


def normalize_uid(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or set(text) == {"0"}:
        return None
    return text


def upsert_spool(conn: sqlite3.Connection, observed_at: str, tray: dict[str, Any]) -> int | None:
    tag_uid = normalize_uid(tray.get("tag_uid"))
    tray_uuid = normalize_uid(tray.get("tray_uuid"))
    if not tag_uid and not tray_uuid:
        return None

    clauses: list[str] = []
    params: list[str] = []
    if tag_uid:
        clauses.append("tag_uid = ?")
        params.append(tag_uid)
    if tray_uuid:
        clauses.append("tray_uuid = ?")
        params.append(tray_uuid)
    existing = conn.execute(
        f"SELECT id FROM spools WHERE {' OR '.join(clauses)} ORDER BY id LIMIT 1",
        params,
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE spools
            SET tag_uid = COALESCE(?, tag_uid),
                tray_uuid = COALESCE(?, tray_uuid),
                filament_id = COALESCE(?, filament_id),
                material_type = COALESCE(?, material_type),
                sub_brand = COALESCE(?, sub_brand),
                color_hex = COALESCE(?, color_hex),
                nominal_weight_g = COALESCE(?, nominal_weight_g),
                diameter_mm = COALESCE(?, diameter_mm),
                last_seen_at = ?
            WHERE id = ?
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
                existing[0],
            ),
        )
        return int(existing[0])

    conn.execute(
        """
        INSERT INTO spools (
            tag_uid, tray_uuid, filament_id, material_type, sub_brand, color_hex,
            nominal_weight_g, diameter_mm, first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Bambu probe data into SQLite.")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--db", type=Path, default=Path("data/spool_tracker.db"))
    args = parser.parse_args()

    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    observed_at, status = first_status(capture)
    printer_serial = capture.get("serial_redacted")
    inserted_observations = 0
    upserted_spools = 0

    with sqlite3.connect(args.db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for ams in status.get("ams", {}).get("ams", []):
            ams_id = str(ams.get("id", ""))
            for tray in ams.get("tray", []):
                slot_id = str(tray.get("id", ""))
                if not slot_id:
                    continue
                spool_id = upsert_spool(conn, observed_at, tray)
                if spool_id:
                    upserted_spools += 1
                conn.execute(
                    """
                    INSERT INTO ams_slot_observations (
                        observed_at, printer_serial, ams_id, slot_id, tag_uid, tray_uuid,
                        material_type, sub_brand, color_hex, remain_percent,
                        total_len_mm, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observed_at,
                        printer_serial,
                        ams_id,
                        slot_id,
                        normalize_uid(tray.get("tag_uid")),
                        normalize_uid(tray.get("tray_uuid")),
                        tray.get("tray_type"),
                        tray.get("tray_sub_brands"),
                        tray.get("tray_color"),
                        as_float(tray.get("remain")),
                        as_float(tray.get("total_len")),
                        json.dumps(tray, sort_keys=True),
                    ),
                )
                inserted_observations += 1

    print(
        f"Imported {inserted_observations} slot observation(s); "
        f"matched/created {upserted_spools} identified spool(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
