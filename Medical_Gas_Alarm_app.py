import tkinter as tk
from tkinter import messagebox
import serial
import serial.tools.list_ports
import threading
import json
import time


APP_TITLE = "Medical Gas Alarm Monitor"

PICO_USB_VID = 0x2E8A
PICO_USB_PID = 0x0005

SERIAL_BAUDRATE = 115200
RECONNECT_INTERVAL_SECONDS = 2
FALLBACK_PORT = "COM3"


class MedicalGasMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1180x720")
        self.root.minsize(1100, 650)
        self.root.configure(bg="#dceef7")

        self.serial_connection = None
        self.serial_thread = None

        self.running = True
        self.connected = False
        self.current_port = None

        self.oxygen_alarm = False
        self.air_alarm = False
        self.vacuum_alarm = False
        self.muted = False
        self.test_active = False
        self.alarm_active = False

        self.blink_state = False
        self.last_data_time = 0

        self.monitor_frame = tk.Frame(self.root, bg="#dceef7")
        self.settings_frame = tk.Frame(self.root, bg="#dceef7")

        self.create_monitor_ui()
        self.create_settings_ui()

        self.show_monitor_page()

        self.start_serial_worker()
        self.blink_alarm()
        self.connection_watchdog()

    # =====================================================
    # PAGE CONTROL
    # =====================================================

    def show_monitor_page(self):
        self.settings_frame.pack_forget()
        self.monitor_frame.pack(fill="both", expand=True)

    def show_settings_page(self):
        self.monitor_frame.pack_forget()
        self.settings_frame.pack(fill="both", expand=True)

    # =====================================================
    # MONITOR UI
    # =====================================================

    def create_monitor_ui(self):
        title = tk.Label(
            self.monitor_frame,
            text="MEDICAL GAS ALARM",
            font=("Arial", 32, "bold"),
            bg="#dceef7",
            fg="black"
        )
        title.pack(pady=(20, 18))

        cards_frame = tk.Frame(self.monitor_frame, bg="#dceef7")
        cards_frame.pack(pady=10)

        self.oxygen_card = self.create_gas_card(
            parent=cards_frame,
            title="OXYGEN",
            unit="PSI",
            column=0,
            style_type="oxygen"
        )

        self.air_card = self.create_gas_card(
            parent=cards_frame,
            title="AIR 4 BAR",
            unit="PSI",
            column=1,
            style_type="air"
        )

        self.vacuum_card = self.create_gas_card(
            parent=cards_frame,
            title="VACUUM",
            unit="mmHg",
            column=2,
            style_type="vacuum"
        )

        bottom_frame = tk.Frame(self.monitor_frame, bg="#dceef7")
        bottom_frame.pack(pady=22)

        self.overall_status = tk.Label(
            bottom_frame,
            text="SYSTEM STATUS: WAITING",
            font=("Arial", 18, "bold"),
            bg="white",
            fg="black",
            width=28,
            height=2,
            relief="solid",
            bd=3
        )
        self.overall_status.grid(row=0, column=0, padx=10)

        self.buzzer_status = tk.Label(
            bottom_frame,
            text="BUZZER: ACTIVE",
            font=("Arial", 18, "bold"),
            bg="white",
            fg="black",
            width=18,
            height=2,
            relief="solid",
            bd=3
        )
        self.buzzer_status.grid(row=0, column=1, padx=10)
        settings_btn = tk.Button(
            bottom_frame,
            text="Settings",
            font=("Arial", 14, "bold"),
            bg="#0b63ce",
            fg="white",
            width=24,
            height=2,
            command=self.show_settings_page
            )
        settings_btn.grid(row=0, column=2, padx=10)
        # self.mode_status = tk.Label(
        #     bottom_frame,
        #     text="LIVE MODE",
        #     font=("Arial", 18, "bold"),
        #     bg="white",
        #     fg="black",
        #     width=16,
        #     height=2,
        #     relief="solid",
        #     bd=3
        # )
        # self.mode_status.grid(row=0, column=2, padx=10)

        # controls_frame = tk.Frame(self.monitor_frame, bg="#dceef7")
        # controls_frame.pack(pady=(3, 8))

        # settings_btn = tk.Button(
        #     controls_frame,
        #     text="Wi-Fi / Email Settings",
        #     font=("Arial", 14, "bold"),
        #     bg="#0b63ce",
        #     fg="white",
        #     width=24,
        #     height=2,
        #     command=self.show_settings_page
        # )
        # settings_btn.grid(row=0, column=0, padx=10)

        self.bottom_connection_label = tk.Label(
            self.monitor_frame,
            text="Medical Gas Alarm Not Connected",
            font=("Arial", 13, "bold"),
            bg="#dceef7",
            fg="#b36b00"
        )
        self.bottom_connection_label.pack(pady=(5, 4))

        self.port_label = tk.Label(
            self.monitor_frame,
            text="Port: Not connected",
            font=("Arial", 11),
            bg="#dceef7",
            fg="black"
        )
        self.port_label.pack()

    # =====================================================
    # GAS CARD DESIGN
    # =====================================================

    def create_gas_card(self, parent, title, unit, column, style_type):
        card_w = 320
        card_h = 430

        if style_type == "vacuum":
            outer_bg = "#f5d321"
        else:
            outer_bg = "white"

        outer = tk.Frame(
            parent,
            width=card_w,
            height=card_h,
            bg=outer_bg,
            relief="solid",
            bd=3
        )
        outer.grid(row=0, column=column, padx=14)
        outer.grid_propagate(False)
        outer.pack_propagate(False)

        # AIR vertical split background
        if style_type == "air":
            tk.Frame(
                outer,
                bg="white"
            ).place(
                x=0,
                y=0,
                width=card_w // 2,
                height=card_h
            )

            tk.Frame(
                outer,
                bg="black"
            ).place(
                x=card_w // 2,
                y=0,
                width=card_w // 2,
                height=card_h
            )

        # -------------------------------
        # TITLE AREA
        # -------------------------------

        if style_type == "air":
            tk.Frame(
                outer,
                bg="#444444",
                height=2
            ).place(x=20, y=39, width=70)

            tk.Frame(
                outer,
                bg="white",
                height=2
            ).place(x=245, y=39, width=55)

            tk.Label(
                outer,
                text="AIR",
                font=("Arial", 20, "bold"),
                bg="white",
                fg="black"
            ).place(x=93, y=17, width=65, height=42)

            tk.Label(
                outer,
                text="4 BAR",
                font=("Arial", 20, "bold"),
                bg="black",
                fg="white"
            ).place(x=162, y=17, width=85, height=42)

        else:
            title_bg = "#f5d321" if style_type == "vacuum" else "white"

            tk.Frame(
                outer,
                bg="#444444",
                height=2
            ).place(x=20, y=39, width=95)

            tk.Frame(
                outer,
                bg="#444444",
                height=2
            ).place(x=205, y=39, width=95)

            tk.Label(
                outer,
                text=title,
                font=("Arial", 20, "bold"),
                bg=title_bg,
                fg="black"
            ).place(x=95, y=17, width=130, height=42)

        # -------------------------------
        # VALUE BOX
        # -------------------------------

        value_box = tk.Frame(
            outer,
            bg="white",
            relief="solid",
            bd=2
        )
        value_box.place(x=25, y=85, width=270, height=170)

        value_label = tk.Label(
            value_box,
            text="--",
            font=("Arial", 72, "bold"),
            bg="white",
            fg="black"
        )
        value_label.pack(expand=True, fill="both")

        # -------------------------------
        # UNIT AREA
        # -------------------------------

        if style_type == "air":
            tk.Frame(
                outer,
                bg="#444444",
                height=2
            ).place(x=25, y=286, width=95)

            tk.Frame(
                outer,
                bg="white",
                height=2
            ).place(x=200, y=286, width=95)

            unit_bg = "black"
            unit_fg = "white"

        else:
            unit_bg = "#f5d321" if style_type == "vacuum" else "white"
            unit_fg = "black"

            tk.Frame(
                outer,
                bg="#444444",
                height=2
            ).place(x=25, y=286, width=95)

            tk.Frame(
                outer,
                bg="#444444",
                height=2
            ).place(x=200, y=286, width=95)

        tk.Label(
            outer,
            text=unit,
            font=("Arial", 22, "bold"),
            bg=unit_bg,
            fg=unit_fg
        ).place(x=120, y=266, width=100, height=40)

        # -------------------------------
        # STATUS BOX
        # -------------------------------

        status_label = tk.Label(
            outer,
            text="WAITING",
            font=("Arial", 20, "bold"),
            bg="#cfeccb",
            fg="#007000",
            relief="solid",
            bd=2
        )
        status_label.place(x=25, y=345, width=270, height=55)

        return {
            "outer": outer,
            "value_box": value_box,
            "value": value_label,
            "status": status_label,
            "style_type": style_type
        }

    # =====================================================
    # SETTINGS UI
    # =====================================================

    def create_settings_ui(self):
        title = tk.Label(
            self.settings_frame,
            text="WI-FI / EMAIL SETTINGS",
            font=("Arial", 30, "bold"),
            bg="#dceef7",
            fg="black"
        )
        title.pack(pady=(40, 20))

        form = tk.Frame(
            self.settings_frame,
            bg="white",
            relief="solid",
            bd=4
        )
        form.pack(pady=20, ipadx=45, ipady=35)

        tk.Label(
            form,
            text="Wi-Fi SSID:",
            font=("Arial", 16, "bold"),
            bg="white"
        ).grid(row=0, column=0, sticky="e", padx=12, pady=15)

        self.ssid_entry = tk.Entry(
            form,
            font=("Arial", 16),
            width=32
        )
        self.ssid_entry.grid(row=0, column=1, padx=12, pady=15)

        tk.Label(
            form,
            text="Wi-Fi Password:",
            font=("Arial", 16, "bold"),
            bg="white"
        ).grid(row=1, column=0, sticky="e", padx=12, pady=15)

        self.password_entry = tk.Entry(
            form,
            font=("Arial", 16),
            width=32,
            show="*"
        )
        self.password_entry.grid(row=1, column=1, padx=12, pady=15)

        tk.Label(
            form,
            text="Receiver Email:",
            font=("Arial", 16, "bold"),
            bg="white"
        ).grid(row=2, column=0, sticky="e", padx=12, pady=15)

        self.email_entry = tk.Entry(
            form,
            font=("Arial", 16),
            width=32
        )
        self.email_entry.grid(row=2, column=1, padx=12, pady=15)

        button_frame = tk.Frame(self.settings_frame, bg="#dceef7")
        button_frame.pack(pady=20)

        send_btn = tk.Button(
            button_frame,
            text="Send Settings to Medical Gas Alarm",
            font=("Arial", 14, "bold"),
            bg="#008000",
            fg="white",
            width=32,
            height=2,
            command=self.send_settings_to_pico
        )
        send_btn.grid(row=0, column=0, padx=10)

        back_btn = tk.Button(
            button_frame,
            text="Back to Monitor",
            font=("Arial", 14, "bold"),
            bg="#333333",
            fg="white",
            width=18,
            height=2,
            command=self.show_monitor_page
        )
        back_btn.grid(row=0, column=1, padx=10)

        self.settings_status = tk.Label(
            self.settings_frame,
            text="",
            font=("Arial", 13, "bold"),
            bg="#dceef7",
            fg="black"
        )
        self.settings_status.pack(pady=10)

    def send_settings_to_pico(self):
        ssid = self.ssid_entry.get().strip()
        password = self.password_entry.get().strip()
        email = self.email_entry.get().strip()

        if not ssid:
            messagebox.showerror("Missing SSID", "Please enter Wi-Fi SSID.")
            return

        if not password:
            messagebox.showerror("Missing Password", "Please enter Wi-Fi password.")
            return

        if not email:
            messagebox.showerror("Missing Email", "Please enter receiver email.")
            return

        if not self.connected or not self.serial_connection:
            messagebox.showerror(
                "Not Connected",
                "Medical Gas Alarm is not connected."
            )
            return

        config = {
            "type": "config",
            "ssid": ssid,
            "password": password,
            "receiver_email": email
        }

        try:
            line = "CONFIG:" + json.dumps(config) + "\n"
            self.serial_connection.write(line.encode("utf-8"))

            self.settings_status.config(
                text="Settings sent to Medical Gas Alarm.",
                fg="green"
            )

        except Exception as e:
            self.settings_status.config(
                text=f"Failed to send settings: {e}",
                fg="red"
            )

    # =====================================================
    # PICO AUTO DETECTION
    # =====================================================

    def find_pico_port(self):
        ports = list(serial.tools.list_ports.comports())

        for port in ports:
            if port.vid == PICO_USB_VID:
                return port.device

            if port.vid == PICO_USB_VID and port.pid == PICO_USB_PID:
                return port.device

            hwid = str(port.hwid).upper()
            if "2E8A" in hwid:
                return port.device

        for port in ports:
            if port.device.upper() == FALLBACK_PORT.upper():
                return FALLBACK_PORT

        return None

    # =====================================================
    # SERIAL WORKER
    # =====================================================

    def start_serial_worker(self):
        self.serial_thread = threading.Thread(
            target=self.serial_worker_loop,
            daemon=True
        )
        self.serial_thread.start()

    def serial_worker_loop(self):
        while self.running:
            if not self.connected:
                self.try_connect_to_pico()
                time.sleep(RECONNECT_INTERVAL_SECONDS)
            else:
                self.read_from_pico()

    def try_connect_to_pico(self):
        port = self.find_pico_port()

        if not port:
            self.root.after(
                0,
                self.set_disconnected_ui,
                "Medical Gas Alarm Not Connected"
            )
            return

        try:
            self.serial_connection = serial.Serial(
                port=port,
                baudrate=SERIAL_BAUDRATE,
                timeout=1
            )

            self.connected = True
            self.current_port = port
            self.last_data_time = time.time()

            self.root.after(
                0,
                self.set_connected_ui,
                port
            )

        except Exception:
            self.connected = False
            self.current_port = None

            try:
                if self.serial_connection:
                    self.serial_connection.close()
            except Exception:
                pass

            self.serial_connection = None

            self.root.after(
                0,
                self.set_disconnected_ui,
                "Medical Gas Alarm found but could not connect"
            )

    def read_from_pico(self):
        try:
            if not self.serial_connection:
                self.connected = False
                return

            line = self.serial_connection.readline().decode(
                "utf-8",
                errors="ignore"
            ).strip()

            if not line:
                return

            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                self.last_data_time = time.time()

                self.root.after(
                    0,
                    self.update_display,
                    data
                )

        except Exception:
            self.handle_serial_disconnect()

    def handle_serial_disconnect(self):
        self.connected = False
        self.current_port = None

        try:
            if self.serial_connection:
                self.serial_connection.close()
        except Exception:
            pass

        self.serial_connection = None

        self.root.after(
            0,
            self.set_disconnected_ui,
            "Medical Gas Alarm disconnected. Reconnecting..."
        )

    def connection_watchdog(self):
        if self.connected:
            if time.time() - self.last_data_time > 5:
                self.handle_serial_disconnect()

        self.root.after(1000, self.connection_watchdog)

    # =====================================================
    # UI UPDATES
    # =====================================================

    def set_connected_ui(self, port):
        self.bottom_connection_label.config(
            text="Connected to Medical Gas Alarm",
            fg="green"
        )

        self.port_label.config(
            text=f"Port: {port}"
        )

    def set_disconnected_ui(self, message):
        self.bottom_connection_label.config(
            text=message,
            fg="#b36b00"
        )

        self.port_label.config(
            text="Port: Not connected"
        )

    def update_display(self, data):
        oxygen = data.get("oxygen", "--")
        air = data.get("air", "--")
        vacuum = data.get("vacuum", "--")

        self.oxygen_alarm = bool(data.get("oxygen_alarm", False))
        self.air_alarm = bool(data.get("air_alarm", False))
        self.vacuum_alarm = bool(data.get("vacuum_alarm", False))
        self.alarm_active = bool(data.get("alarm_active", False))

        self.muted = bool(data.get("muted", False))
        self.test_active = bool(data.get("test_active", False))

        self.oxygen_card["value"].config(text=str(oxygen))
        self.air_card["value"].config(text=str(air))
        self.vacuum_card["value"].config(text=str(vacuum))

        self.update_status_label(self.oxygen_card, self.oxygen_alarm)
        self.update_status_label(self.air_card, self.air_alarm)
        self.update_status_label(self.vacuum_card, self.vacuum_alarm)

        if self.alarm_active:
            self.overall_status.config(
                text="SYSTEM STATUS: LOW PRESSURE",
                bg="#ffd4d4",
                fg="red"
            )
        else:
            self.overall_status.config(
                text="SYSTEM STATUS: NORMAL",
                bg="#d8f5d0",
                fg="#006400"
            )

        if self.muted:
            self.buzzer_status.config(
                text="BUZZER: MUTED",
                bg="#fff1c7",
                fg="#8a5a00"
            )
        else:
            if self.alarm_active:
                self.buzzer_status.config(
                    text="BUZZER: ACTIVE",
                    bg="#ffd4d4",
                    fg="red"
                )
            else:
                self.buzzer_status.config(
                    text="BUZZER: ACTIVE",
                    bg="white",
                    fg="black"
                )

        # if self.test_active:
        #     self.mode_status.config(
        #         text="TEST MODE",
        #         bg="#d9e8ff",
        #         fg="#003d99"
        #     )
        # else:
        #     self.mode_status.config(
        #         text="LIVE MODE",
        #         bg="white",
        #         fg="black"
        #     )

    def update_status_label(self, card, alarm):
        if alarm:
            card["status"].config(
                text="LOW PRESSURE",
                bg="#ffd4d4",
                fg="red"
            )
        else:
            card["status"].config(
                text="NORMAL",
                bg="#cfeccb",
                fg="#007000"
            )

    def blink_alarm(self):
        self.blink_state = not self.blink_state

        alarm_cards = [
            (self.oxygen_card, self.oxygen_alarm),
            (self.air_card, self.air_alarm),
            (self.vacuum_card, self.vacuum_alarm)
        ]

        for card, alarm in alarm_cards:
            if alarm:
                if self.blink_state:
                    card["value"].config(fg="red")
                    card["status"].config(bg="#ffd4d4", fg="red")
                else:
                    card["value"].config(fg="white")
                    card["status"].config(bg="white", fg="white")
            else:
                card["value"].config(fg="black")
                card["status"].config(bg="#cfeccb", fg="#007000")

        self.root.after(500, self.blink_alarm)

    # =====================================================
    # CLOSE APP
    # =====================================================

    def on_close(self):
        self.running = False

        try:
            if self.serial_connection:
                self.serial_connection.close()
        except Exception:
            pass

        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MedicalGasMonitorApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()