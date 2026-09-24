"""Connect to Panel 01 and display its newline-delimited JSON telemetry."""

import json
import socket
import time
from datetime import datetime


PANEL_IP = "192.168.10.101"
PANEL_PORT = 5050
RECONNECT_SECONDS = 2


def receive_telemetry(connection):
    buffer = b""

    while True:
        chunk = connection.recv(4096)
        if not chunk:
            raise ConnectionError("Panel closed the connection")

        buffer += chunk
        while b"\n" in buffer:
            raw_line, buffer = buffer.split(b"\n", 1)
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            data = json.loads(raw_line.decode("utf-8"))
            panel = data.get("panel_name", data.get("panel_id", "Unknown"))
            alarm = "ALARM" if data.get("alarm_active") else "NORMAL"
            print(
                f"[{datetime.now():%H:%M:%S}] {panel}: "
                f"O2={data.get('oxygen', '--')} PSI, "
                f"Air={data.get('air', '--')} PSI, "
                f"Vacuum={data.get('vacuum', '--')} mmHg, {alarm}"
            )


def main():
    print(f"Connecting to Panel 01 at {PANEL_IP}:{PANEL_PORT}")
    print("Press Ctrl+C to stop.\n")

    while True:
        connection = None
        try:
            connection = socket.create_connection((PANEL_IP, PANEL_PORT), timeout=3)
            connection.settimeout(5)
            print(f"[{datetime.now():%H:%M:%S}] Panel 01 connected")
            receive_telemetry(connection)
        except KeyboardInterrupt:
            print("\nReceiver stopped.")
            return
        except (OSError, ConnectionError, json.JSONDecodeError) as error:
            print(f"[{datetime.now():%H:%M:%S}] Waiting for Panel 01: {error}")
            time.sleep(RECONNECT_SECONDS)
        finally:
            if connection is not None:
                connection.close()


if __name__ == "__main__":
    main()
