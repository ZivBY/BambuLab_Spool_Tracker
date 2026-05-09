from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from tools.tracker_store import (
    connect_db,
    dashboard_snapshot,
    init_schema,
    record_printer_message,
)


DEFAULT_MQTT_PORT = 8883
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class BambuWatcher(threading.Thread):
    def __init__(self, host: str, serial: str, access_code: str, db_path: Path, port: int) -> None:
        super().__init__(daemon=True)
        self.host = host
        self.serial = serial
        self.access_code = access_code
        self.db_path = db_path
        self.port = port
        self.stop_event = threading.Event()
        self.client: mqtt.Client | None = None
        self.last_message_at = 0.0

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._run_once()
            except Exception as exc:
                print(f"Watcher error: {exc}", file=sys.stderr)
            if not self.stop_event.is_set():
                time.sleep(5)

    def stop(self) -> None:
        self.stop_event.set()
        if self.client:
            self.client.disconnect()

    def _run_once(self) -> None:
        report_topic = REPORT_TOPIC_TEMPLATE.format(serial=self.serial)
        request_topic = REQUEST_TOPIC_TEMPLATE.format(serial=self.serial)
        safe_serial = self.serial[:4] + "..." + self.serial[-4:]

        def on_connect(client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
            if reason_code_value(reason_code) != 0:
                print(f"MQTT connection failed with reason code {reason_code}", file=sys.stderr)
                return
            print(f"Watcher connected to {self.host}:{self.port} for {safe_serial}")
            client.subscribe(report_topic, qos=0)
            client.publish(request_topic, make_pushall_payload(int(time.time())), qos=0)

        def on_message(_client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
            try:
                payload = json.loads(message.payload.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                return
            with connect_db(self.db_path) as conn:
                init_schema(conn)
                observations, identified = record_printer_message(conn, utc_now(), safe_serial, payload)
                self.last_message_at = time.time()
                if observations:
                    print(f"Watcher recorded {observations} slot(s), {identified} identified spool(s).")

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"bambu-spool-watch-{int(time.time())}",
            protocol=mqtt.MQTTv311,
        )
        self.client = client
        client.username_pw_set("bblp", self.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self.host, self.port, keepalive=60)

        last_pushall_at = 0.0
        while not self.stop_event.is_set():
            client.loop(timeout=1.0)
            now = time.time()
            if now - last_pushall_at >= 30:
                client.publish(request_topic, make_pushall_payload(int(now)), qos=0)
                last_pushall_at = now
            if self.last_message_at and now - self.last_message_at > 180:
                raise RuntimeError("No printer status received for 180 seconds; reconnecting watcher")


class TrackerHandler(SimpleHTTPRequestHandler):
    db_path: Path
    static_root: Path

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        relative = parsed.path.lstrip("/") or "index.html"
        return str(self.static_root / relative)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json(dashboard_snapshot(self.db_path))
            return
        if parsed.path == "/health":
            self.send_json({"ok": True})
            return
        super().do_GET()

    def send_json(self, data: dict[str, Any]) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Bambu spool tracker watcher and UI.")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--db", type=Path, default=Path("data/spool_tracker.db"))
    parser.add_argument("--http-host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8050)
    parser.add_argument("--mqtt-port", type=int, default=DEFAULT_MQTT_PORT)
    parser.add_argument("--no-watcher", action="store_true")
    args = parser.parse_args()

    load_env(args.env)
    host = require_env("BAMBU_HOST")
    serial = require_env("BAMBU_SERIAL")
    access_code = require_env("BAMBU_ACCESS_CODE")

    with connect_db(args.db) as conn:
        init_schema(conn)

    watcher = None
    if not args.no_watcher:
        watcher = BambuWatcher(host, serial, access_code, args.db, args.mqtt_port)
        watcher.start()

    TrackerHandler.db_path = args.db
    TrackerHandler.static_root = Path(__file__).parent / "web"
    server = ThreadingHTTPServer((args.http_host, args.http_port), TrackerHandler)
    print(f"UI available at http://{args.http_host}:{args.http_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if watcher:
            watcher.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
