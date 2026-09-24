# Medical Gas Alarm

Complete medical-gas monitoring project for up to 20 Ethernet panels and 60 sensors.

## Included

- Raspberry Pi Pico W/W5500 panel firmware (`main.py`)
- TJC HMI projects, backgrounds, fonts, and button assets
- Windows multi-panel desktop dashboard
- Local read-only web dashboard
- AWS cloud receiver and read-only web dashboard
- Test receiver and setup documentation
- Pico and W5500 MicroPython firmware images

## Configuration

`dashboard_config.json` defines the panel IDs, names, fixed IP addresses, TCP port, and offline timeout.

The live `web_config.json` and `cloud_config.json` files are intentionally excluded from Git because they contain private tokens and session secrets. Copy their `.example.json` versions, remove `.example` from the filenames, and replace each placeholder. The ingest token must match in both files.

Generate a password hash and random secrets with:

```powershell
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('YOUR_PASSWORD'))"
python -c "import secrets; print(secrets.token_hex(32)); print(secrets.token_urlsafe(32))"
```

## Main documentation

- `WEB_DASHBOARD_SETUP.md` — local Windows web dashboard
- `AWS_DEPLOYMENT.md` — AWS/Ubuntu public dashboard
- `TJC_HMI_COMPONENTS.md` — TJC display component names and behavior
