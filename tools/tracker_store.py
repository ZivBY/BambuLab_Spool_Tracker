from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
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


def estimated_remaining_g(tray: dict[str, Any]) -> float | None:
    remain_percent = as_float(tray.get("remain"))
    nominal_weight_g = as_float(tray.get("tray_weight"))
    if remain_percent is None or not nominal_weight_g or remain_percent < 0:
        return None
    return nominal_weight_g * remain_percent / 100


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
    migrate_schema(conn)


def migrate_schema(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(filament_drying_events)").fetchall()}
    additions = {
        "start_humidity_percent": "REAL",
        "end_humidity_percent": "REAL",
        "actual_duration_minutes": "REAL",
    }
    for column, column_type in additions.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE filament_drying_events ADD COLUMN {column} {column_type}")
    spool_columns = {row["name"] for row in conn.execute("PRAGMA table_info(spools)").fetchall()}
    spool_additions = {
        "last_remain_percent": "REAL",
        "last_estimated_remaining_g": "REAL",
        "deleted_at": "TEXT",
    }
    for column, column_type in spool_additions.items():
        if column not in spool_columns:
            conn.execute(f"ALTER TABLE spools ADD COLUMN {column} {column_type}")
    manual_override_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(ams_slot_manual_filaments)").fetchall()
    }
    if "spool_id" not in manual_override_columns:
        conn.execute("ALTER TABLE ams_slot_manual_filaments ADD COLUMN spool_id INTEGER REFERENCES spools(id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manual_filaments (
            id INTEGER PRIMARY KEY,
            label TEXT NOT NULL UNIQUE,
            last_remain_percent REAL,
            last_estimated_remaining_g REAL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            deleted_at TEXT
        )
        """
    )
    manual_columns = {row["name"] for row in conn.execute("PRAGMA table_info(manual_filaments)").fetchall()}
    if "deleted_at" not in manual_columns:
        conn.execute("ALTER TABLE manual_filaments ADD COLUMN deleted_at TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS filament_drying_event_spools (
            id INTEGER PRIMARY KEY,
            drying_event_id INTEGER NOT NULL REFERENCES filament_drying_events(id) ON DELETE CASCADE,
            spool_id INTEGER NOT NULL REFERENCES spools(id),
            slot_id TEXT,
            source TEXT NOT NULL DEFAULT 'rfid',
            created_at TEXT NOT NULL,
            UNIQUE(drying_event_id, spool_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_filament_drying_event_spools_event
        ON filament_drying_event_spools(drying_event_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS filament_drying_event_slots (
            drying_event_id INTEGER NOT NULL REFERENCES filament_drying_events(id) ON DELETE CASCADE,
            slot_id TEXT NOT NULL,
            spool_id INTEGER REFERENCES spools(id),
            manual_filament_label TEXT,
            ams_filament_label TEXT,
            status TEXT NOT NULL DEFAULT 'unknown',
            source TEXT NOT NULL DEFAULT 'unknown',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (drying_event_id, slot_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ams_slot_manual_filaments (
            ams_id TEXT NOT NULL,
            slot_id TEXT NOT NULL,
            spool_id INTEGER REFERENCES spools(id),
            manual_filament_label TEXT,
            marked_empty INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (ams_id, slot_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_filament_drying_event_slots_event
        ON filament_drying_event_slots(drying_event_id)
        """
    )
    dedupe_spools(conn)
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_spools_tag_uid_unique
        ON spools(tag_uid)
        WHERE tag_uid IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_spools_tray_uuid_unique
        ON spools(tray_uuid)
        WHERE tray_uuid IS NOT NULL
        """
    )
    reconcile_partial_drying_assignments(conn)


def reconcile_partial_drying_assignments(conn: sqlite3.Connection) -> None:
    now = datetime.now(timezone.utc).isoformat()
    events = conn.execute(
        """
        SELECT id, spool_id, manual_filament_label
        FROM filament_drying_events
        WHERE spool_id IS NOT NULL OR manual_filament_label IS NOT NULL
        """
    ).fetchall()
    for event in events:
        unknown_slots = conn.execute(
            """
            SELECT slot_id
            FROM filament_drying_event_slots
            WHERE drying_event_id = ? AND status = 'unknown'
            ORDER BY CAST(slot_id AS INTEGER)
            """,
            (event["id"],),
        ).fetchall()
        if len(unknown_slots) != 1:
            continue
        slot_id = unknown_slots[0]["slot_id"]
        if event["spool_id"] is not None:
            conn.execute(
                """
                UPDATE filament_drying_event_slots
                SET spool_id = ?, manual_filament_label = NULL, status = 'rfid',
                    source = 'manual', updated_at = ?
                WHERE drying_event_id = ? AND slot_id = ?
                """,
                (event["spool_id"], now, event["id"], slot_id),
            )
        elif event["manual_filament_label"]:
            conn.execute(
                """
                UPDATE filament_drying_event_slots
                SET manual_filament_label = ?, status = 'manual',
                    source = 'manual', updated_at = ?
                WHERE drying_event_id = ? AND slot_id = ?
                """,
                (event["manual_filament_label"], now, event["id"], slot_id),
            )


def merge_duplicate_spool(conn: sqlite3.Connection, keeper_id: int, duplicate_id: int) -> None:
    if keeper_id == duplicate_id:
        return
    duplicate = conn.execute("SELECT * FROM spools WHERE id = ?", (duplicate_id,)).fetchone()
    if not duplicate:
        return
    conn.execute(
        """
        UPDATE spools
        SET tag_uid = COALESCE(tag_uid, ?),
            tray_uuid = COALESCE(tray_uuid, ?),
            filament_id = COALESCE(filament_id, ?),
            material_type = COALESCE(material_type, ?),
            sub_brand = COALESCE(sub_brand, ?),
            color_hex = COALESCE(color_hex, ?),
            nominal_weight_g = COALESCE(nominal_weight_g, ?),
            diameter_mm = COALESCE(diameter_mm, ?),
            last_remain_percent = COALESCE(last_remain_percent, ?),
            last_estimated_remaining_g = COALESCE(last_estimated_remaining_g, ?),
            first_seen_at = MIN(first_seen_at, ?),
            last_seen_at = MAX(last_seen_at, ?)
        WHERE id = ?
        """,
        (
            duplicate["tag_uid"],
            duplicate["tray_uuid"],
            duplicate["filament_id"],
            duplicate["material_type"],
            duplicate["sub_brand"],
            duplicate["color_hex"],
            duplicate["nominal_weight_g"],
            duplicate["diameter_mm"],
            duplicate["last_remain_percent"],
            duplicate["last_estimated_remaining_g"],
            duplicate["first_seen_at"],
            duplicate["last_seen_at"],
            keeper_id,
        ),
    )
    conn.execute("UPDATE spool_usage_events SET spool_id = ? WHERE spool_id = ?", (keeper_id, duplicate_id))
    conn.execute("UPDATE filament_drying_events SET spool_id = ? WHERE spool_id = ?", (keeper_id, duplicate_id))
    conn.execute("UPDATE filament_drying_event_slots SET spool_id = ? WHERE spool_id = ?", (keeper_id, duplicate_id))
    linked_rows = conn.execute(
        """
        SELECT drying_event_id, slot_id, source, created_at
        FROM filament_drying_event_spools
        WHERE spool_id = ?
        """,
        (duplicate_id,),
    ).fetchall()
    for row in linked_rows:
        conn.execute(
            """
            INSERT OR IGNORE INTO filament_drying_event_spools (
                drying_event_id, spool_id, slot_id, source, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (row["drying_event_id"], keeper_id, row["slot_id"], row["source"], row["created_at"]),
        )
    conn.execute("DELETE FROM filament_drying_event_spools WHERE spool_id = ?", (duplicate_id,))
    conn.execute("DELETE FROM spools WHERE id = ?", (duplicate_id,))


def duplicate_spool_group(conn: sqlite3.Connection) -> list[int]:
    for column in ("tag_uid", "tray_uuid"):
        row = conn.execute(
            f"""
            SELECT GROUP_CONCAT(id) AS ids
            FROM (
                SELECT id, {column}
                FROM spools
                WHERE {column} IS NOT NULL
                ORDER BY id
            )
            GROUP BY {column}
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        ).fetchone()
        if row and row["ids"]:
            return [int(value) for value in row["ids"].split(",")]
    return []


def dedupe_spools(conn: sqlite3.Connection) -> None:
    while True:
        ids = duplicate_spool_group(conn)
        if not ids:
            return
        keeper_id = ids[0]
        for duplicate_id in ids[1:]:
            merge_duplicate_spool(conn, keeper_id, duplicate_id)


def matching_spool_ids(conn: sqlite3.Connection, tag_uid: str | None, tray_uuid: str | None) -> list[int]:
    clauses: list[str] = []
    params: list[str] = []
    if tag_uid:
        clauses.append("tag_uid = ?")
        params.append(tag_uid)
    if tray_uuid:
        clauses.append("tray_uuid = ?")
        params.append(tray_uuid)
    if not clauses:
        return []
    rows = conn.execute(
        f"SELECT id FROM spools WHERE {' OR '.join(clauses)} ORDER BY id",
        params,
    ).fetchall()
    return [int(row["id"]) for row in rows]


def update_spool_from_tray(
    conn: sqlite3.Connection,
    spool_id: int,
    observed_at: str,
    tray: dict[str, Any],
    tag_uid: str | None,
    tray_uuid: str | None,
) -> None:
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
            last_remain_percent = COALESCE(?, last_remain_percent),
            last_estimated_remaining_g = COALESCE(?, last_estimated_remaining_g),
            last_seen_at = ?,
            deleted_at = NULL
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
            as_float(tray.get("remain")),
            estimated_remaining_g(tray),
            observed_at,
            spool_id,
        ),
    )


def upsert_spool(conn: sqlite3.Connection, observed_at: str, tray: dict[str, Any]) -> int | None:
    tag_uid = normalize_uid(tray.get("tag_uid"))
    tray_uuid = normalize_uid(tray.get("tray_uuid"))
    if not tag_uid and not tray_uuid:
        return None

    ids = matching_spool_ids(conn, tag_uid, tray_uuid)
    if ids:
        spool_id = ids[0]
        for duplicate_id in ids[1:]:
            merge_duplicate_spool(conn, spool_id, duplicate_id)
        update_spool_from_tray(conn, spool_id, observed_at, tray, tag_uid, tray_uuid)
        return spool_id

    conn.execute(
        """
        INSERT INTO spools (
            tag_uid, tray_uuid, filament_id, material_type, sub_brand, color_hex,
            nominal_weight_g, diameter_mm, last_remain_percent,
            last_estimated_remaining_g, first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            as_float(tray.get("remain")),
            estimated_remaining_g(tray),
            observed_at,
            observed_at,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def spool_display_name(row: sqlite3.Row | dict[str, Any] | None) -> str:
    if not row:
        return "Unassigned filament"
    material = row["material_type"] or "Filament"
    brand = row["sub_brand"] or ""
    label = " - ".join(part for part in (brand, material) if part)
    return label or "Filament"


def upsert_manual_filament(
    conn: sqlite3.Connection,
    label: str,
    observed_at: str,
    remain_percent: float | None = None,
    remaining_g: float | None = None,
) -> int | None:
    text = label.strip()
    if not text:
        return None
    conn.execute(
        """
        INSERT INTO manual_filaments (
            label, last_remain_percent, last_estimated_remaining_g, first_seen_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(label) DO UPDATE SET
            last_remain_percent = COALESCE(excluded.last_remain_percent, manual_filaments.last_remain_percent),
            last_estimated_remaining_g = COALESCE(excluded.last_estimated_remaining_g, manual_filaments.last_estimated_remaining_g),
            last_seen_at = excluded.last_seen_at,
            deleted_at = NULL
        """,
        (text, remain_percent, remaining_g, observed_at, observed_at),
    )
    row = conn.execute("SELECT id FROM manual_filaments WHERE label = ?", (text,)).fetchone()
    return int(row["id"]) if row else None


def find_spool_id_for_tray(conn: sqlite3.Connection, observed_at: str, tray: dict[str, Any]) -> int | None:
    tag_uid = normalize_uid(tray.get("tag_uid"))
    tray_uuid = normalize_uid(tray.get("tray_uuid"))
    if not tag_uid and not tray_uuid:
        return None
    return upsert_spool(conn, observed_at, tray)


def drying_spool_from_ams(conn: sqlite3.Connection, observed_at: str, ams: dict[str, Any]) -> tuple[int | None, str | None]:
    spools = drying_spools_from_ams(conn, observed_at, ams)
    if not spools:
        return None, None
    first = spools[0]
    return int(first["spool_id"]), str(first["slot_id"])


def tray_has_filament(tray: dict[str, Any]) -> bool:
    return bool(
        tray.get("tray_type")
        or tray.get("tray_sub_brands")
        or normalize_uid(tray.get("tag_uid"))
        or normalize_uid(tray.get("tray_uuid"))
    )


def tray_ams_label(tray: dict[str, Any]) -> str | None:
    parts = [tray.get("tray_sub_brands"), tray.get("tray_type")]
    label = " - ".join(str(part).strip() for part in parts if str(part or "").strip())
    return label or None


def drying_spools_from_ams(conn: sqlite3.Connection, observed_at: str, ams: dict[str, Any]) -> list[dict[str, Any]]:
    spools: list[dict[str, Any]] = []
    seen: set[int] = set()
    for tray in ams.get("tray", []):
        if not tray_has_filament(tray):
            continue
        spool_id = find_spool_id_for_tray(conn, observed_at, tray)
        if not spool_id or spool_id in seen:
            continue
        seen.add(spool_id)
        spools.append({"spool_id": spool_id, "slot_id": str(tray.get("id", "0"))})
    return spools


def drying_slots_from_ams(conn: sqlite3.Connection, observed_at: str, ams: dict[str, Any]) -> list[dict[str, Any]]:
    ams_id = str(ams.get("id", ""))
    slots: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tray in ams.get("tray", []):
        slot_id = str(tray.get("id", ""))
        if not slot_id or slot_id in seen:
            continue
        seen.add(slot_id)
        spool_id = find_spool_id_for_tray(conn, observed_at, tray)
        ams_label = tray_ams_label(tray)
        loaded = tray_has_filament(tray)
        override = conn.execute(
            """
            SELECT spool_id, manual_filament_label, marked_empty
            FROM ams_slot_manual_filaments
            WHERE ams_id = ? AND slot_id = ?
            """,
            (ams_id, slot_id),
        ).fetchone()
        if spool_id:
            slots.append({
                "slot_id": slot_id,
                "spool_id": spool_id,
                "manual_filament_label": None,
                "ams_filament_label": ams_label,
                "status": "rfid",
                "source": "rfid",
            })
        elif override and override["spool_id"]:
            slots.append({
                "slot_id": slot_id,
                "spool_id": int(override["spool_id"]),
                "manual_filament_label": None,
                "ams_filament_label": ams_label,
                "status": "rfid",
                "source": "manual",
            })
        elif override and override["manual_filament_label"]:
            slots.append({
                "slot_id": slot_id,
                "spool_id": None,
                "manual_filament_label": override["manual_filament_label"],
                "ams_filament_label": ams_label,
                "status": "manual",
                "source": "manual",
            })
        elif override and override["marked_empty"]:
            slots.append({
                "slot_id": slot_id,
                "spool_id": None,
                "manual_filament_label": None,
                "ams_filament_label": ams_label,
                "status": "empty",
                "source": "manual",
            })
        elif loaded:
            slots.append({
                "slot_id": slot_id,
                "spool_id": None,
                "manual_filament_label": None,
                "ams_filament_label": ams_label,
                "status": "unknown",
                "source": "ams",
            })
        else:
            slots.append({
                "slot_id": slot_id,
                "spool_id": None,
                "manual_filament_label": None,
                "ams_filament_label": None,
                "status": "unknown",
                "source": "ams",
            })
    return slots


def sync_drying_event_spools(
    conn: sqlite3.Connection,
    event_id: int,
    observed_at: str,
    spools: list[dict[str, Any]],
    source: str = "rfid",
) -> None:
    if not spools:
        return
    for spool in spools:
        conn.execute(
            """
            INSERT INTO filament_drying_event_spools (
                drying_event_id, spool_id, slot_id, source, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(drying_event_id, spool_id) DO UPDATE SET
                slot_id = excluded.slot_id,
                source = excluded.source
            """,
            (event_id, spool["spool_id"], spool.get("slot_id"), spool.get("source", source), observed_at),
        )


def sync_drying_event_slots(
    conn: sqlite3.Connection,
    event_id: int,
    observed_at: str,
    slots: list[dict[str, Any]],
) -> None:
    for slot in slots:
        conn.execute(
            """
            INSERT INTO filament_drying_event_slots (
                drying_event_id, slot_id, spool_id, manual_filament_label,
                ams_filament_label, status, source, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(drying_event_id, slot_id) DO UPDATE SET
                spool_id = excluded.spool_id,
                manual_filament_label = excluded.manual_filament_label,
                ams_filament_label = excluded.ams_filament_label,
                status = excluded.status,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                event_id,
                slot["slot_id"],
                slot.get("spool_id"),
                slot.get("manual_filament_label"),
                slot.get("ams_filament_label"),
                slot["status"],
                slot["source"],
                observed_at,
            ),
        )


def humidity_percent_from_ams(ams: dict[str, Any]) -> float | None:
    value = as_float(ams.get("humidity_raw"))
    if value is not None:
        return value
    return as_float(ams.get("humidity"))


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def elapsed_minutes(started_at: str | None, ended_at: str | None) -> float | None:
    start = parse_timestamp(started_at)
    end = parse_timestamp(ended_at)
    if not start or not end:
        return None
    return max(0, round((end - start).total_seconds() / 60, 1))


def dry_setting_has_cycle(dry_setting: dict[str, Any]) -> bool:
    return any(
        dry_setting.get(key) not in (None, "", -1, "-1")
        for key in ("dry_filament", "dry_temperature", "dry_duration")
    )


def record_drying_event(conn: sqlite3.Connection, observed_at: str, ams: dict[str, Any]) -> None:
    ams_id = str(ams.get("id", ""))
    if not ams_id:
        return

    dry_time = as_int(ams.get("dry_time")) or 0
    active_row = conn.execute(
        """
        SELECT id, spool_id, attribution_source, started_at
        FROM filament_drying_events
        WHERE ams_id = ? AND ended_at IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (ams_id,),
    ).fetchone()

    if dry_time <= 0:
        if active_row:
            actual_duration = elapsed_minutes(active_row["started_at"], observed_at)
            conn.execute(
                """
                UPDATE filament_drying_events
                SET ended_at = ?, last_seen_at = ?, last_remaining_minutes = 0,
                    end_humidity_percent = ?, actual_duration_minutes = ?,
                    raw_json = ?
                WHERE id = ?
                """,
                (
                    observed_at,
                    observed_at,
                    humidity_percent_from_ams(ams),
                    actual_duration,
                    json.dumps(ams, sort_keys=True),
                    active_row["id"],
                ),
            )
        return

    dry_setting = ams.get("dry_setting") or {}
    if not active_row and not dry_setting_has_cycle(dry_setting):
        return

    event_slots = drying_slots_from_ams(conn, observed_at, ams)
    event_spools = [
        {"spool_id": slot["spool_id"], "slot_id": slot["slot_id"], "source": slot.get("source", "rfid")}
        for slot in event_slots
        if slot.get("spool_id")
    ]
    spool_id = int(event_spools[0]["spool_id"]) if event_spools else None
    slot_id = str(event_spools[0]["slot_id"]) if event_spools else None
    attribution = "rfid" if any(spool.get("source") == "rfid" for spool in event_spools) else "manual" if event_spools else "unassigned"
    raw_json = json.dumps(ams, sort_keys=True)

    if active_row:
        next_spool_id = active_row["spool_id"] or spool_id
        next_attribution = active_row["attribution_source"]
        if next_attribution == "unassigned" and spool_id:
            next_attribution = attribution
        conn.execute(
            """
            UPDATE filament_drying_events
            SET spool_id = ?, slot_id = COALESCE(slot_id, ?),
                attribution_source = ?,
                dry_filament = COALESCE(NULLIF(?, ''), dry_filament),
                dry_temperature_c = COALESCE(?, dry_temperature_c),
                dry_duration_hours = COALESCE(?, dry_duration_hours),
                start_humidity_percent = COALESCE(start_humidity_percent, ?),
                last_seen_at = ?, last_remaining_minutes = ?, raw_json = ?
            WHERE id = ?
            """,
            (
                next_spool_id,
                slot_id,
                next_attribution,
                dry_setting.get("dry_filament"),
                as_float(dry_setting.get("dry_temperature")),
                as_float(dry_setting.get("dry_duration")),
                humidity_percent_from_ams(ams),
                observed_at,
                dry_time,
                raw_json,
                active_row["id"],
            ),
        )
        sync_drying_event_spools(conn, int(active_row["id"]), observed_at, event_spools)
        sync_drying_event_slots(conn, int(active_row["id"]), observed_at, event_slots)
        return

    cursor = conn.execute(
        """
        INSERT INTO filament_drying_events (
            ams_id, slot_id, spool_id, attribution_source, dry_filament,
            dry_temperature_c, dry_duration_hours, started_at, last_seen_at,
            start_remaining_minutes, last_remaining_minutes, start_humidity_percent,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ams_id,
            slot_id,
            spool_id,
            attribution,
            dry_setting.get("dry_filament"),
            as_float(dry_setting.get("dry_temperature")),
            as_float(dry_setting.get("dry_duration")),
            observed_at,
            observed_at,
            dry_time,
            dry_time,
            humidity_percent_from_ams(ams),
            raw_json,
        ),
    )
    sync_drying_event_spools(conn, int(cursor.lastrowid), observed_at, event_spools)
    sync_drying_event_slots(conn, int(cursor.lastrowid), observed_at, event_slots)


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
        record_drying_event(conn, observed_at, ams)
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
            remaining_g = estimated_remaining_g(tray)

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
                    remaining_g,
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


def assign_drying_event(
    db_path: Path,
    event_id: int,
    spool_id: int | None = None,
    manual_filament_label: str | None = None,
    slot_assignments: list[dict[str, Any]] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    label = (manual_filament_label or "").strip() or None
    with connect_db(db_path) as conn:
        init_schema(conn)
        event = conn.execute(
            "SELECT id, ams_id, slot_id FROM filament_drying_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if not event:
            raise ValueError("Drying event was not found.")

        slot_labels: list[str] = []
        slot_spools: list[dict[str, Any]] = []
        if slot_assignments:
            for assignment in slot_assignments:
                now = datetime.now(timezone.utc).isoformat()
                slot_id = str(assignment.get("slot_id", "")).strip()
                if not slot_id:
                    continue
                marked_empty = bool(assignment.get("marked_empty"))
                raw_slot_spool_id = assignment.get("spool_id")
                slot_spool_id = int(raw_slot_spool_id) if str(raw_slot_spool_id or "").isdigit() else None
                slot_label = str(assignment.get("manual_filament_label") or assignment.get("label") or "").strip()
                if not marked_empty and slot_spool_id is None and not slot_label:
                    continue
                if slot_spool_id is not None:
                    spool = conn.execute("SELECT id FROM spools WHERE id = ?", (slot_spool_id,)).fetchone()
                    if not spool:
                        raise ValueError("Selected spool was not found.")
                    slot_spools.append({"spool_id": slot_spool_id, "slot_id": slot_id})
                    slot_label = ""
                    slot_status = "rfid"
                elif marked_empty:
                    slot_label = ""
                    slot_status = "empty"
                else:
                    slot_labels.append(slot_label)
                    current_slot = conn.execute(
                        """
                        SELECT remain_percent, estimated_remaining_g
                        FROM current_ams_slots
                        WHERE ams_id = ? AND slot_id = ?
                        """,
                        (event["ams_id"], slot_id),
                    ).fetchone()
                    upsert_manual_filament(
                        conn,
                        slot_label,
                        datetime.now(timezone.utc).isoformat(),
                        current_slot["remain_percent"] if current_slot else None,
                        current_slot["estimated_remaining_g"] if current_slot else None,
                    )
                    slot_status = "manual"
                conn.execute(
                    """
                    INSERT INTO ams_slot_manual_filaments (
                        ams_id, slot_id, spool_id, manual_filament_label, marked_empty, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ams_id, slot_id) DO UPDATE SET
                        spool_id = excluded.spool_id,
                        manual_filament_label = excluded.manual_filament_label,
                        marked_empty = excluded.marked_empty,
                        updated_at = excluded.updated_at
                    """,
                    (
                        event["ams_id"],
                        slot_id,
                        slot_spool_id,
                        slot_label or None,
                        1 if marked_empty else 0,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO filament_drying_event_slots (
                        drying_event_id, slot_id, spool_id, manual_filament_label,
                        ams_filament_label, status, source, updated_at
                    )
                    VALUES (?, ?, ?, ?, NULL, ?, 'manual', ?)
                    ON CONFLICT(drying_event_id, slot_id) DO UPDATE SET
                        spool_id = excluded.spool_id,
                        manual_filament_label = excluded.manual_filament_label,
                        status = excluded.status,
                        source = 'manual',
                        updated_at = excluded.updated_at
                    """,
                    (
                        event_id,
                        slot_id,
                        slot_spool_id,
                        slot_label or None,
                        slot_status,
                        now,
                    ),
                )
            if slot_labels and not label:
                label = " | ".join(slot_labels)
            if slot_spools:
                sync_drying_event_spools(conn, event_id, datetime.now(timezone.utc).isoformat(), slot_spools, source="manual")

        if spool_id is not None:
            spool = conn.execute("SELECT id FROM spools WHERE id = ?", (spool_id,)).fetchone()
            if not spool:
                raise ValueError("Selected spool was not found.")
            source = "manual"
            label = None
        elif slot_spools:
            spool_id = int(slot_spools[0]["spool_id"])
            source = "manual"
            label = None
        elif label or slot_assignments:
            source = "manual"
        else:
            raise ValueError("Choose a spool or enter a filament label.")

        result = conn.execute(
            """
            UPDATE filament_drying_events
            SET spool_id = ?, manual_filament_label = ?, attribution_source = ?,
                note = COALESCE(?, note)
            WHERE id = ?
            """,
            (spool_id, label, source, note, event_id),
        )
        if result.rowcount == 0:
            raise ValueError("Drying event was not found.")
        unresolved_slots = [
            str(row["slot_id"])
            for row in conn.execute(
                """
                SELECT slot_id
                FROM filament_drying_event_slots
                WHERE drying_event_id = ? AND status = 'unknown'
                ORDER BY CAST(slot_id AS INTEGER)
                """,
                (event_id,),
            ).fetchall()
        ]
        fallback_slot_id = str(event["slot_id"]) if event["slot_id"] is not None else (
            unresolved_slots[0] if len(unresolved_slots) == 1 else None
        )
        if label and not slot_assignments and event["slot_id"] is not None:
            now = datetime.now(timezone.utc).isoformat()
            current_slot = conn.execute(
                """
                SELECT remain_percent, estimated_remaining_g
                FROM current_ams_slots
                WHERE ams_id = ? AND slot_id = ?
                """,
                (event["ams_id"], event["slot_id"]),
            ).fetchone()
            upsert_manual_filament(
                conn,
                label,
                now,
                current_slot["remain_percent"] if current_slot else None,
                current_slot["estimated_remaining_g"] if current_slot else None,
            )
            conn.execute(
                """
                INSERT INTO ams_slot_manual_filaments (
                    ams_id, slot_id, spool_id, manual_filament_label, marked_empty, updated_at
                )
                VALUES (?, ?, NULL, ?, 0, ?)
                ON CONFLICT(ams_id, slot_id) DO UPDATE SET
                    spool_id = NULL,
                    manual_filament_label = excluded.manual_filament_label,
                    marked_empty = 0,
                    updated_at = excluded.updated_at
                """,
                (event["ams_id"], event["slot_id"], label, now),
            )
            conn.execute(
                """
                UPDATE filament_drying_event_slots
                SET manual_filament_label = ?, status = 'manual',
                    source = 'manual', updated_at = ?
                WHERE drying_event_id = ? AND slot_id = ?
                """,
                (label, now, event_id, event["slot_id"]),
            )
        elif label and not slot_assignments and fallback_slot_id is not None:
            now = datetime.now(timezone.utc).isoformat()
            current_slot = conn.execute(
                """
                SELECT remain_percent, estimated_remaining_g
                FROM current_ams_slots
                WHERE ams_id = ? AND slot_id = ?
                """,
                (event["ams_id"], fallback_slot_id),
            ).fetchone()
            upsert_manual_filament(
                conn,
                label,
                now,
                current_slot["remain_percent"] if current_slot else None,
                current_slot["estimated_remaining_g"] if current_slot else None,
            )
            conn.execute(
                """
                INSERT INTO ams_slot_manual_filaments (
                    ams_id, slot_id, spool_id, manual_filament_label, marked_empty, updated_at
                )
                VALUES (?, ?, NULL, ?, 0, ?)
                ON CONFLICT(ams_id, slot_id) DO UPDATE SET
                    spool_id = NULL,
                    manual_filament_label = excluded.manual_filament_label,
                    marked_empty = 0,
                    updated_at = excluded.updated_at
                """,
                (event["ams_id"], fallback_slot_id, label, now),
            )
            conn.execute(
                """
                UPDATE filament_drying_event_slots
                SET manual_filament_label = ?, status = 'manual',
                    source = 'manual', updated_at = ?
                WHERE drying_event_id = ? AND slot_id = ?
                """,
                (label, now, event_id, fallback_slot_id),
            )
        if spool_id is not None and not slot_assignments and event["slot_id"] is not None:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO ams_slot_manual_filaments (
                    ams_id, slot_id, spool_id, manual_filament_label, marked_empty, updated_at
                )
                VALUES (?, ?, ?, NULL, 0, ?)
                ON CONFLICT(ams_id, slot_id) DO UPDATE SET
                    spool_id = excluded.spool_id,
                    manual_filament_label = NULL,
                    marked_empty = 0,
                    updated_at = excluded.updated_at
                """,
                (event["ams_id"], event["slot_id"], spool_id, now),
            )
            sync_drying_event_spools(
                conn,
                event_id,
                now,
                [{"spool_id": spool_id, "slot_id": event["slot_id"]}],
                source="manual",
            )
            conn.execute(
                """
                UPDATE filament_drying_event_slots
                SET spool_id = ?, manual_filament_label = NULL, status = 'rfid',
                    source = 'manual', updated_at = ?
                WHERE drying_event_id = ? AND slot_id = ?
                """,
                (spool_id, now, event_id, event["slot_id"]),
            )
        elif spool_id is not None and not slot_assignments and fallback_slot_id is not None:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO ams_slot_manual_filaments (
                    ams_id, slot_id, spool_id, manual_filament_label, marked_empty, updated_at
                )
                VALUES (?, ?, ?, NULL, 0, ?)
                ON CONFLICT(ams_id, slot_id) DO UPDATE SET
                    spool_id = excluded.spool_id,
                    manual_filament_label = NULL,
                    marked_empty = 0,
                    updated_at = excluded.updated_at
                """,
                (event["ams_id"], fallback_slot_id, spool_id, now),
            )
            conn.execute(
                """
                UPDATE filament_drying_event_slots
                SET spool_id = ?, manual_filament_label = NULL, status = 'rfid',
                    source = 'manual', updated_at = ?
                WHERE drying_event_id = ? AND slot_id = ?
                """,
                (spool_id, now, event_id, fallback_slot_id),
            )
            sync_drying_event_spools(
                conn,
                event_id,
                now,
                [{"spool_id": spool_id, "slot_id": fallback_slot_id}],
                source="manual",
            )
        conn.commit()

    return dashboard_snapshot(db_path)


def clean_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def clean_color_hex(value: Any) -> str | None:
    text = str(value or "").strip().lstrip("#")
    if not text:
        return None
    if len(text) != 6 or any(char not in "0123456789abcdefABCDEF" for char in text):
        raise ValueError("Color must be a 6-digit hex value.")
    return text.upper()


def update_inventory_item(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    inventory_id = str(payload.get("inventory_id") or "").strip()
    if not inventory_id:
        raise ValueError("Missing inventory item.")

    material_type = clean_optional_text(payload.get("material_type"))
    label = clean_optional_text(payload.get("label"))
    color_hex = clean_color_hex(payload.get("color_hex"))
    remain_percent = as_float(payload.get("remain_percent"))
    if remain_percent is not None and (remain_percent < 0 or remain_percent > 100):
        raise ValueError("Remaining percent must be between 0 and 100.")

    with connect_db(db_path) as conn:
        init_schema(conn)
        if inventory_id.startswith("manual:"):
            raw_id = inventory_id.split(":", 1)[1]
            if not raw_id.isdigit():
                raise ValueError("Invalid manual inventory item.")
            manual_id = int(raw_id)
            if not label:
                raise ValueError("Manual inventory items need a label.")
            result = conn.execute(
                """
                UPDATE manual_filaments
                SET label = ?,
                    last_remain_percent = ?,
                    last_seen_at = ?
                WHERE id = ?
                  AND deleted_at IS NULL
                """,
                (label, remain_percent, datetime.now(timezone.utc).isoformat(), manual_id),
            )
            if result.rowcount == 0:
                raise ValueError("Inventory item was not found.")
        else:
            if not inventory_id.isdigit():
                raise ValueError("Invalid inventory item.")
            spool_id = int(inventory_id)
            result = conn.execute(
                """
                UPDATE spools
                SET material_type = ?,
                    sub_brand = ?,
                    color_hex = ?,
                    last_remain_percent = ?,
                    last_seen_at = ?
                WHERE id = ?
                  AND deleted_at IS NULL
                """,
                (
                    material_type,
                    label,
                    color_hex,
                    remain_percent,
                    datetime.now(timezone.utc).isoformat(),
                    spool_id,
                ),
            )
            if result.rowcount == 0:
                raise ValueError("Inventory item was not found.")
        conn.commit()

    return dashboard_snapshot(db_path)


def delete_inventory_item(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    inventory_id = str(payload.get("inventory_id") or "").strip()
    if not inventory_id:
        raise ValueError("Missing inventory item.")

    with connect_db(db_path) as conn:
        init_schema(conn)
        now = datetime.now(timezone.utc).isoformat()
        if inventory_id.startswith("manual:"):
            raw_id = inventory_id.split(":", 1)[1]
            if not raw_id.isdigit():
                raise ValueError("Invalid manual inventory item.")
            manual_id = int(raw_id)
            row = conn.execute(
                "SELECT label FROM manual_filaments WHERE id = ? AND deleted_at IS NULL",
                (manual_id,),
            ).fetchone()
            if not row:
                raise ValueError("Inventory item was not found.")
            conn.execute(
                """
                DELETE FROM ams_slot_manual_filaments
                WHERE spool_id IS NULL
                  AND manual_filament_label = ?
                """,
                (row["label"],),
            )
            conn.execute("DELETE FROM manual_filaments WHERE id = ?", (manual_id,))
        else:
            if not inventory_id.isdigit():
                raise ValueError("Invalid inventory item.")
            spool_id = int(inventory_id)
            row = conn.execute(
                """
                SELECT id, tag_uid, tray_uuid
                FROM spools
                WHERE id = ? AND deleted_at IS NULL
                """,
                (spool_id,),
            ).fetchone()
            if not row:
                raise ValueError("Inventory item was not found.")
            current_clauses: list[str] = []
            current_params: list[Any] = []
            if row["tag_uid"]:
                current_clauses.append("tag_uid = ?")
                current_params.append(row["tag_uid"])
            if row["tray_uuid"]:
                current_clauses.append("tray_uuid = ?")
                current_params.append(row["tray_uuid"])
            current_row = None
            if current_clauses:
                current_row = conn.execute(
                    f"""
                    SELECT ams_id, slot_id
                    FROM current_ams_slots
                    WHERE {' OR '.join(current_clauses)}
                    LIMIT 1
                    """,
                    current_params,
                ).fetchone()
            if current_row:
                raise ValueError("Unload this RFID spool before deleting it from inventory.")
            conn.execute(
                """
                DELETE FROM ams_slot_manual_filaments
                WHERE spool_id = ?
                """,
                (spool_id,),
            )
            conn.execute(
                """
                UPDATE spools
                SET deleted_at = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (now, now, spool_id),
            )
        conn.commit()

    return dashboard_snapshot(db_path)


def dashboard_snapshot(db_path: Path) -> dict[str, Any]:
    with connect_db(db_path) as conn:
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
                SELECT s.*, COALESCE(latest.remain_percent, manual_latest.remain_percent, s.last_remain_percent) AS remain_percent,
                       COALESCE(latest.estimated_remaining_g, manual_latest.estimated_remaining_g, s.last_estimated_remaining_g) AS estimated_remaining_g,
                       COALESCE(latest.ams_id, manual_latest.ams_id) AS ams_id,
                       COALESCE(latest.slot_id, manual_latest.slot_id) AS slot_id,
                       CASE WHEN COALESCE(latest.ams_id, manual_latest.ams_id) IS NULL THEN 0 ELSE 1 END AS is_loaded,
                       'rfid' AS inventory_source,
                       CAST(s.id AS TEXT) AS inventory_id,
                       NULL AS manual_label
                FROM spools s
                LEFT JOIN (
                    SELECT tag_uid, tray_uuid, remain_percent, estimated_remaining_g, ams_id, slot_id
                    FROM current_ams_slots
                    WHERE tag_uid IS NOT NULL OR tray_uuid IS NOT NULL
                ) latest
                  ON latest.tag_uid IS s.tag_uid AND latest.tray_uuid IS s.tray_uuid
                LEFT JOIN (
                    SELECT manual.spool_id, current.remain_percent, current.estimated_remaining_g,
                           current.ams_id, current.slot_id
                    FROM ams_slot_manual_filaments manual
                    JOIN current_ams_slots current
                      ON current.ams_id = manual.ams_id AND current.slot_id = manual.slot_id
                    WHERE manual.spool_id IS NOT NULL
                      AND manual.marked_empty = 0
                      AND current.tag_uid IS NULL
                      AND current.tray_uuid IS NULL
                      AND (
                          current.material_type IS NOT NULL
                          OR current.sub_brand IS NOT NULL
                          OR current.remain_percent IS NOT NULL
                      )
                ) manual_latest
                  ON manual_latest.spool_id = s.id
                WHERE s.deleted_at IS NULL
                ORDER BY s.last_seen_at DESC
                """
            ).fetchall()
        )
        manual_spools = rows_as_dicts(
            conn.execute(
                """
                SELECT mf.id, NULL AS tag_uid, NULL AS tray_uuid, NULL AS filament_id,
                       NULL AS material_type, mf.label AS sub_brand, NULL AS color_hex,
                       NULL AS nominal_weight_g, NULL AS diameter_mm,
                       COALESCE(current.remain_percent, mf.last_remain_percent) AS remain_percent,
                       COALESCE(current.estimated_remaining_g, mf.last_estimated_remaining_g) AS estimated_remaining_g,
                       current.ams_id, current.slot_id,
                       CASE WHEN current.ams_id IS NULL THEN 0 ELSE 1 END AS is_loaded,
                       'manual' AS inventory_source,
                       'manual:' || CAST(mf.id AS TEXT) AS inventory_id,
                       mf.label AS manual_label,
                       mf.first_seen_at, mf.last_seen_at
                FROM manual_filaments mf
                LEFT JOIN (
                    SELECT manual.ams_id, manual.slot_id, manual.manual_filament_label,
                           current.remain_percent, current.estimated_remaining_g
                    FROM ams_slot_manual_filaments manual
                    LEFT JOIN current_ams_slots current
                      ON current.ams_id = manual.ams_id AND current.slot_id = manual.slot_id
                    WHERE manual.marked_empty = 0
                      AND manual.spool_id IS NULL
                      AND manual.manual_filament_label IS NOT NULL
                      AND current.tag_uid IS NULL
                      AND current.tray_uuid IS NULL
                ) current
                  ON current.manual_filament_label = mf.label
                WHERE mf.deleted_at IS NULL
                ORDER BY mf.last_seen_at DESC
                """
            ).fetchall()
        )
        spools.extend(manual_spools)
        drying_events = rows_as_dicts(
            conn.execute(
                """
                SELECT d.id, d.ams_id, d.slot_id, d.spool_id, d.attribution_source,
                       d.manual_filament_label, d.dry_filament, d.dry_temperature_c,
                       d.dry_duration_hours, d.started_at, d.last_seen_at, d.ended_at,
                       d.start_remaining_minutes, d.last_remaining_minutes,
                       d.start_humidity_percent, d.end_humidity_percent,
                       d.actual_duration_minutes, d.note,
                       s.tag_uid, s.tray_uuid, s.material_type, s.sub_brand, s.color_hex
                FROM filament_drying_events d
                LEFT JOIN spools s ON s.id = d.spool_id
                ORDER BY d.ended_at IS NOT NULL, d.started_at DESC
                LIMIT 30
                """
            ).fetchall()
        )
        drying_event_slots: dict[int, list[dict[str, Any]]] = {}
        drying_event_spools: dict[int, list[dict[str, Any]]] = {}
        event_ids = [int(event["id"]) for event in drying_events]
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            slot_rows = rows_as_dicts(
                conn.execute(
                    f"""
                    SELECT slots.drying_event_id, slots.slot_id, slots.source, slots.status,
                           slots.manual_filament_label, slots.ams_filament_label,
                           s.id AS spool_id, s.tag_uid, s.tray_uuid, s.material_type,
                           s.sub_brand, s.color_hex
                    FROM filament_drying_event_slots slots
                    LEFT JOIN spools s ON s.id = slots.spool_id
                    WHERE slots.drying_event_id IN ({placeholders})
                    ORDER BY CAST(slots.slot_id AS INTEGER)
                    """,
                    event_ids,
                ).fetchall()
            )
            for row in slot_rows:
                if row.get("spool_id"):
                    row["filament_label"] = spool_display_name(row)
                elif row.get("status") == "manual":
                    row["filament_label"] = row.get("manual_filament_label") or "Manual filament"
                elif row.get("status") == "empty":
                    row["filament_label"] = "Empty"
                else:
                    slot_label = f"Slot {int(row['slot_id']) + 1} needs input"
                    row["filament_label"] = f"{slot_label} ({row['ams_filament_label']})" if row.get("ams_filament_label") else slot_label
                drying_event_slots.setdefault(int(row["drying_event_id"]), []).append(row)
            linked_rows = rows_as_dicts(
                conn.execute(
                    f"""
                    SELECT des.drying_event_id, des.slot_id, des.source,
                           s.id AS spool_id, s.tag_uid, s.tray_uuid, s.material_type,
                           s.sub_brand, s.color_hex
                    FROM filament_drying_event_spools des
                    JOIN spools s ON s.id = des.spool_id
                    WHERE des.drying_event_id IN ({placeholders})
                    ORDER BY CAST(des.slot_id AS INTEGER), des.id
                    """,
                    event_ids,
                ).fetchall()
            )
            for row in linked_rows:
                row["status"] = "rfid"
                row["filament_label"] = spool_display_name(row)
                drying_event_spools.setdefault(int(row["drying_event_id"]), []).append(row)
        for event in drying_events:
            linked_slots = drying_event_slots.get(int(event["id"]), []) or drying_event_spools.get(int(event["id"]), [])
            event["filaments"] = linked_slots
            needs_slot_input = any(slot.get("status") == "unknown" for slot in linked_slots)
            event["needs_slot_input"] = needs_slot_input
            if linked_slots:
                used_manual_autofill = needs_slot_input and event.get("manual_filament_label")
                if used_manual_autofill:
                    event["filament_label"] = event["manual_filament_label"]
                    event["needs_slot_input"] = False
                else:
                    visible_labels = [
                        slot["filament_label"]
                        for slot in linked_slots
                        if slot.get("status") != "empty"
                    ]
                    event["filament_label"] = " | ".join(visible_labels) or "Empty"
                if event.get("needs_slot_input"):
                    event["attribution_source"] = "unassigned"
                elif used_manual_autofill or any(slot.get("status") == "manual" or slot.get("source") == "manual" for slot in linked_slots):
                    event["attribution_source"] = "manual"
                else:
                    event["attribution_source"] = "rfid"
            elif event.get("spool_id"):
                event["filament_label"] = spool_display_name(event)
            else:
                event["filament_label"] = event.get("manual_filament_label") or event.get("dry_filament") or "Needs filament"
            event["elapsed_duration_minutes"] = event.get("actual_duration_minutes")
            if event["elapsed_duration_minutes"] is None and not event.get("ended_at"):
                event["elapsed_duration_minutes"] = elapsed_minutes(event.get("started_at"), datetime.now(timezone.utc).isoformat())
        active_drying_by_ams = {
            str(event["ams_id"]): event
            for event in drying_events
            if not event.get("ended_at")
        }
        for unit in ams_units:
            active_event = active_drying_by_ams.get(str(unit.get("ams_id")))
            if active_event:
                unit["drying_event_id"] = active_event["id"]
                unit["drying_event_filament_label"] = active_event["filament_label"]
                unit["drying_event_attribution_source"] = active_event["attribution_source"]
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
        "drying_events": drying_events,
        "recent_observations": recent,
    }
