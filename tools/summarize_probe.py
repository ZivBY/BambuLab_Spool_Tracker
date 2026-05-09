from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def first_print_payload(capture: dict[str, Any]) -> dict[str, Any]:
    for message in capture.get("messages", []):
        payload = message.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("print"), dict):
            return payload["print"]
    raise RuntimeError("No printer status payload found in capture.")


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize a Bambu probe capture.")
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()

    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    status = first_print_payload(capture)
    ams_root = status.get("ams", {})
    ams_units = ams_root.get("ams", [])

    print("Printer")
    print(f"  job_state: {clean(status.get('gcode_state'))}")
    print(f"  progress: {clean(status.get('mc_percent'))}%")
    print(f"  print_type: {clean(status.get('print_type'))}")
    print(f"  subtask: {clean(status.get('subtask_name'))}")
    print(f"  gcode_file: {clean(status.get('gcode_file'))}")
    print()

    print("AMS Units")
    for ams in ams_units:
        unit_id = clean(ams.get("id"))
        humidity = clean(ams.get("humidity"))
        temp = clean(ams.get("temp"))
        print(f"  AMS {unit_id}: humidity={humidity} temp={temp}")
        for tray in ams.get("tray", []):
            tray_id = clean(tray.get("id"))
            tag_uid = clean(tray.get("tag_uid"))
            filament_id = clean(tray.get("tray_info_idx"))
            filament_type = clean(tray.get("tray_type"))
            color = clean(tray.get("tray_color"))
            bed_temp = clean(tray.get("bed_temp"))
            nozzle_temp = clean(tray.get("nozzle_temp_max"))
            k_value = clean(tray.get("k"))
            remaining = clean(tray.get("remain"))
            print(
                "    "
                f"slot={tray_id} tag_uid={tag_uid} "
                f"type={filament_type} color={color} "
                f"filament_id={filament_id} remaining={remaining} "
                f"bed={bed_temp} nozzle_max={nozzle_temp} k={k_value}"
            )
    print()

    vt_tray = status.get("vt_tray", {})
    if vt_tray:
        print("Virtual/External Tray")
        print(json.dumps(vt_tray, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
