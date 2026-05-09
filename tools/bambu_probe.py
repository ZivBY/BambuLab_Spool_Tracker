from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt


DEFAULT_PORT = 8883
REPORT_TOPIC_TEMPLATE = "device/{serial}/report"
REQUEST_TOPIC_TEMPLATE = "device/{serial}/request"


def load_env(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def json_default(value: Any) -> str:
    return repr(value)


def make_pushall_payload(sequence_id: int) -> str:
    return json.dumps(
        {
            "pushing": {
                "sequence_id": str(sequence_id),
                "command": "pushall",
                "version": 1,
                "push_target": 1,
            }
        },
        separators=(",", ":"),
    )


def reason_code_value(reason_code: Any) -> int:
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0 if str(reason_code).lower() == "success" else -1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Bambu Lab local MQTT telemetry probe."
    )
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--out-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    load_env(args.env)
    host = require_env("BAMBU_HOST")
    serial = require_env("BAMBU_SERIAL")
    access_code = require_env("BAMBU_ACCESS_CODE")

    report_topic = REPORT_TOPIC_TEMPLATE.format(serial=serial)
    request_topic = REQUEST_TOPIC_TEMPLATE.format(serial=serial)
    messages: list[dict[str, Any]] = []
    connected = False

    def on_connect(client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
        nonlocal connected
        if reason_code_value(reason_code) != 0:
            print(f"MQTT connection failed with reason code {reason_code}", file=sys.stderr)
            return

        connected = True
        print(f"Connected to {host}:{args.port}; subscribing to {report_topic}")
        client.subscribe(report_topic, qos=0)
        client.publish(request_topic, make_pushall_payload(int(time.time())), qos=0)
        print("Requested full printer state with pushall.")

    def on_message(_client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        payload_text = message.payload.decode("utf-8", errors="replace")
        try:
            payload: Any = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = payload_text

        messages.append(
            {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "topic": message.topic,
                "payload": payload,
            }
        )
        print(f"Received message {len(messages)} on {message.topic}")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"bambu-spool-probe-{utc_stamp()}",
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set("bblp", access_code)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message

    safe_serial = serial[:4] + "..." + serial[-4:] if len(serial) > 8 else "***"
    print(f"Connecting to Bambu printer {safe_serial} at {host}:{args.port}")
    client.connect(host, args.port, keepalive=60)
    client.loop_start()

    deadline = time.time() + max(args.seconds, 1)
    while time.time() < deadline:
        time.sleep(0.25)

    client.loop_stop()
    client.disconnect()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.out_dir / f"bambu_probe_{utc_stamp()}.json"
    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "host": host,
        "serial_redacted": safe_serial,
        "port": args.port,
        "connected": connected,
        "message_count": len(messages),
        "messages": messages,
    }
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=json_default),
        encoding="utf-8",
    )
    print(f"Wrote {len(messages)} message(s) to {output_path}")

    return 0 if connected and messages else 2


if __name__ == "__main__":
    raise SystemExit(main())
