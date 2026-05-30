# Bambu Spool Tracker

Local-first tools for building a spool usage tracker around a Bambu Lab printer and AMS setup.

## Step 1: Probe printer telemetry

The first utility is read-only. It connects to the printer's local MQTT service, requests a full status update, listens briefly, and writes the raw messages to `data/raw/`.

### Printer details needed

Find these on the printer screen:

- Printer IP address
- Printer serial number
- LAN access code

For newer firmware, enable LAN/Developer Mode if local MQTT is not available in the default mode.

### Setup

```powershell
cd "C:\Users\benye\OneDrive\Documents\New project\bambu-spool-tracker"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your printer values.

### Run

```powershell
.\.venv\Scripts\python.exe .\tools\bambu_probe.py --env .env --seconds 20
```

The output file will be written to `data/raw/`.

## Run the live watcher and dashboard

```powershell
cd "C:\Users\benye\OneDrive\Documents\New project\bambu-spool-tracker"
.\scripts\start_tracker.ps1
```

Open `http://127.0.0.1:8050/`.

The app starts a local web server and a background MQTT watcher. It records current AMS slots, RFID spool identities, Bambu's remaining percentage, and estimated remaining grams when the printer reports a nominal spool weight.

Drying and heating cycles are recorded from the AMS `dry_time` and `dry_setting` telemetry. If the AMS payload exposes a spool RFID during the cycle, the tracker links that exact spool automatically. When the AMS does not expose RFID while drying, the Activity panel prompts you to choose a known spool or type the filament label manually.

## Keep it running on Windows

GitHub stores the project, but the live watcher must run on a machine that can reach the printer on the local network.

To start it automatically when you log in:

```powershell
cd "C:\Users\benye\OneDrive\Documents\New project\bambu-spool-tracker"
.\scripts\install_startup_task.ps1
```

The dashboard will be available at `http://127.0.0.1:8050/` while that Windows account is logged in.
