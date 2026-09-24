"""Windows Ethernet dashboard for up to 20 medical-gas alarm panels."""

import json
import queue
import socket
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog


APP_TITLE = "Medical Gas Alarm Dashboard"
CONFIG_PATH = Path(__file__).with_name("dashboard_config.json")

PAGE_BG = "#dceef7"
HEADER_BLUE = "#126fe0"
CARD_BORDER = "#101010"
NORMAL_BG = "#c8f5c5"
NORMAL_FG = "#176000"
ALARM_BG = "#ff8b8b"
ALARM_FG = "#c80000"
OFFLINE_BG = "#d8d8d8"
OFFLINE_FG = "#555555"
VACUUM_YELLOW = "#f5d321"


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    config["listen_port"] = int(config.get("listen_port", 5050))
    config["offline_seconds"] = float(config.get("offline_seconds", 5))
    return config


class PanelState:
    def __init__(self, definition):
        self.panel_id = definition["id"]
        self.name = definition["name"]
        self.ip = definition["ip"]
        self.online = False
        self.last_seen = 0.0
        self.data = {}
        self.error = "Waiting for panel"


class PanelWorker(threading.Thread):
    def __init__(self, state, port, output_queue, stop_event):
        super().__init__(daemon=True)
        self.state = state
        self.port = port
        self.output_queue = output_queue
        self.stop_event = stop_event

    def publish(self, event, **values):
        self.output_queue.put((event, self.state.panel_id, values))

    def run(self):
        while not self.stop_event.is_set():
            connection = None
            try:
                connection = socket.create_connection(
                    (self.state.ip, self.port), timeout=2
                )
                connection.settimeout(4)
                self.publish("connected")
                self.receive_loop(connection)
            except (OSError, ConnectionError, json.JSONDecodeError) as error:
                self.publish("disconnected", error=str(error))
                self.stop_event.wait(2)
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass

    def receive_loop(self, connection):
        buffer = b""
        while not self.stop_event.is_set():
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
                self.publish("telemetry", data=data)


class PanelCard:
    def __init__(self, parent, state, open_callback):
        self.state = state
        self.frame = tk.Frame(
            parent,
            width=270,
            height=145,
            bg="white",
            highlightthickness=2,
            highlightbackground=CARD_BORDER,
            cursor="hand2",
        )
        self.frame.grid_propagate(False)

        self.title = tk.Label(
            self.frame,
            text=state.name,
            font=("Arial", 14, "bold"),
            bg="white",
            anchor="w",
        )
        self.title.place(x=10, y=5, width=160, height=25)

        self.connection = tk.Label(
            self.frame,
            text="OFFLINE",
            font=("Arial", 10, "bold"),
            bg=OFFLINE_BG,
            fg=OFFLINE_FG,
        )
        self.connection.place(x=178, y=5, width=80, height=25)

        self.values = {}
        gas_specs = (
            ("oxygen", "OXYGEN", "PSI", 8, "white", "black"),
            ("air", "AIR 4 BAR", "PSI", 95, "#202020", "white"),
            ("vacuum", "VACUUM", "mmHg", 182, VACUUM_YELLOW, "black"),
        )
        for key, label, unit, x, background, foreground in gas_specs:
            gas = tk.Frame(self.frame, bg=background, highlightthickness=1)
            gas.place(x=x, y=39, width=80, height=94)
            if key == "air":
                tk.Frame(gas, bg="white").place(x=0, y=0, width=40, height=94)
                tk.Frame(gas, bg="#202020").place(x=40, y=0, width=40, height=94)
                tk.Label(
                    gas,
                    text="AIR",
                    font=("Arial", 7, "bold"),
                    bg="white",
                    fg="black",
                ).place(x=0, y=0, width=40, height=18)
                tk.Label(
                    gas,
                    text="4 BAR",
                    font=("Arial", 7, "bold"),
                    bg="#202020",
                    fg="white",
                ).place(x=40, y=0, width=40, height=18)
            else:
                tk.Label(
                    gas,
                    text=label,
                    font=("Arial", 8, "bold"),
                    bg=background,
                    fg=foreground,
                ).place(x=0, y=0, width=80, height=18)
            value = tk.Label(
                gas,
                text="--",
                font=("Arial", 24, "bold"),
                bg="white",
                fg="black",
            )
            value.place(x=3, y=18, width=74, height=58)
            if key == "air":
                left_unit = tk.Canvas(
                    gas, width=40, height=18, bg="white", highlightthickness=0
                )
                left_unit.place(x=0, y=76)
                left_unit.create_text(
                    40, 9, text="PSI", font=("Arial", 8, "bold"), fill="black"
                )
                right_unit = tk.Canvas(
                    gas, width=40, height=18, bg="#202020", highlightthickness=0
                )
                right_unit.place(x=40, y=76)
                right_unit.create_text(
                    0, 9, text="PSI", font=("Arial", 8, "bold"), fill="white"
                )
            else:
                tk.Label(
                    gas,
                    text=unit,
                    font=("Arial", 8, "bold"),
                    bg=background,
                    fg=foreground,
                ).place(x=0, y=76, width=80, height=18)
            self.values[key] = value

        self.bind_click(self.frame, lambda _event: open_callback(state.panel_id))

    def bind_click(self, widget, callback):
        widget.bind("<Button-1>", callback)
        for child in widget.winfo_children():
            self.bind_click(child, callback)

    def grid(self, row, column):
        self.frame.grid(row=row, column=column, padx=7, pady=7)

    def update(self):
        data = self.state.data
        self.title.config(text=self.state.name)

        if not self.state.online:
            self.connection.config(text="OFFLINE", bg=OFFLINE_BG, fg=OFFLINE_FG)
            for value in self.values.values():
                value.config(text="--", fg=OFFLINE_FG)
            self.frame.config(highlightbackground="#777777")
            return

        alarm = bool(data.get("alarm_active", False))
        self.connection.config(
            text="ALARM" if alarm else "ONLINE",
            bg=ALARM_BG if alarm else NORMAL_BG,
            fg=ALARM_FG if alarm else NORMAL_FG,
        )
        self.frame.config(highlightbackground=ALARM_FG if alarm else CARD_BORDER)

        for key, widget in self.values.items():
            widget.config(
                text=str(data.get(key, "--")),
                fg=ALARM_FG if data.get(f"{key}_alarm", False) else "black",
            )

    def apply_blink(self, visible):
        if not self.state.online:
            return

        data = self.state.data
        for key, widget in self.values.items():
            if data.get(f"{key}_alarm", False):
                widget.config(fg=ALARM_FG if visible else "white")
            else:
                widget.config(fg="black")

        if data.get("alarm_active", False):
            self.connection.config(
                bg=ALARM_BG if visible else "white",
                fg=ALARM_FG if visible else "white",
            )


class DashboardApp:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.states = {
            item["id"]: PanelState(item) for item in self.config["panels"]
        }
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.workers = []
        self.cards = {}
        self.current_detail_id = None
        self.visible_panel_ids = None
        self.blink_visible = True

        root.title(APP_TITLE)
        root.geometry("1220x900")
        root.minsize(1120, 700)
        root.configure(bg=PAGE_BG)

        self.overview_page = tk.Frame(root, bg=PAGE_BG)
        self.detail_page = tk.Frame(root, bg=PAGE_BG)

        self.build_overview()
        self.build_detail()
        self.show_overview()
        self.start_workers()

        root.after(100, self.process_events)
        root.after(1000, self.watchdog)
        root.after(1000, self.update_clock)
        root.after(500, self.blink_alarms)

    def build_overview(self):
        header = tk.Frame(self.overview_page, bg=PAGE_BG, height=78)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="MEDICAL GAS ALARM DASHBOARD",
            font=("Arial", 27, "bold"),
            bg=PAGE_BG,
        ).pack(side="left", padx=24, pady=15)

        self.summary = tk.Label(
            header,
            text="0 CONNECTED  |  0 ALARM",
            font=("Arial", 13, "bold"),
            bg=PAGE_BG,
        )
        self.summary.pack(side="right", padx=24)

        self.clock = tk.Label(
            self.overview_page,
            text="",
            font=("Arial", 11),
            bg=PAGE_BG,
        )
        self.clock.pack(anchor="e", padx=25)

        canvas = tk.Canvas(self.overview_page, bg=PAGE_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(
            self.overview_page, orient="vertical", command=canvas.yview
        )
        self.cards_frame = tk.Frame(canvas, bg=PAGE_BG)
        self.cards_frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(22, 0), pady=8)
        scrollbar.pack(side="right", fill="y")

        for index, state in enumerate(self.states.values()):
            card = PanelCard(self.cards_frame, state, self.show_detail)
            self.cards[state.panel_id] = card

        self.empty_message = tk.Label(
            self.cards_frame,
            text="Waiting for connected medical-gas panels...",
            font=("Arial", 18, "bold"),
            bg=PAGE_BG,
            fg="#555555",
        )
        self.refresh_visible_cards()

    def build_detail(self):
        top = tk.Frame(self.detail_page, bg=PAGE_BG, height=78)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Button(
            top,
            text="← ALL PANELS",
            font=("Arial", 13, "bold"),
            bg=HEADER_BLUE,
            fg="white",
            command=self.show_overview,
        ).pack(side="left", padx=22, pady=16)

        self.detail_title = tk.Label(
            top,
            text="PANEL",
            font=("Arial", 28, "bold"),
            bg=PAGE_BG,
        )
        self.detail_title.pack(side="left", padx=25)

        tk.Button(
            top,
            text="EDIT NAME",
            font=("Arial", 11, "bold"),
            bg="white",
            fg="black",
            command=self.edit_current_panel_name,
        ).pack(side="left", padx=4, pady=19)

        self.detail_connection = tk.Label(
            top,
            text="OFFLINE",
            font=("Arial", 13, "bold"),
            bg=OFFLINE_BG,
            fg=OFFLINE_FG,
            width=12,
        )
        self.detail_connection.pack(side="right", padx=25, pady=18)

        cards = tk.Frame(self.detail_page, bg=PAGE_BG)
        cards.pack(expand=True)
        self.detail_gases = {}

        specs = (
            ("oxygen", "OXYGEN", "PSI", "white", "black"),
            ("air", "AIR 4 BAR", "PSI", "#202020", "white"),
            ("vacuum", "VACUUM", "mmHg", VACUUM_YELLOW, "black"),
        )
        for column, (key, label, unit, background, foreground) in enumerate(specs):
            outer = tk.Frame(
                cards,
                width=345,
                height=500,
                bg=background,
                highlightthickness=3,
                highlightbackground=CARD_BORDER,
            )
            outer.grid(row=0, column=column, padx=10)
            outer.grid_propagate(False)

            if key == "air":
                tk.Frame(outer, bg="white").place(x=0, y=0, width=171, height=500)
                tk.Frame(outer, bg="#202020").place(x=171, y=0, width=174, height=500)
                tk.Label(
                    outer,
                    text="AIR",
                    font=("Arial", 25, "bold"),
                    bg="white",
                    fg="black",
                    anchor="e",
                ).place(x=12, y=15, width=159, height=52)
                tk.Label(
                    outer,
                    text="4 BAR",
                    font=("Arial", 25, "bold"),
                    bg="#202020",
                    fg="white",
                    anchor="w",
                ).place(x=171, y=15, width=162, height=52)
            else:
                tk.Label(
                    outer,
                    text=label,
                    font=("Arial", 25, "bold"),
                    bg=background,
                    fg=foreground,
                ).place(x=12, y=15, width=315, height=52)

            value = tk.Label(
                outer,
                text="--",
                font=("Arial", 82, "bold"),
                bg="white",
                fg="black",
                relief="solid",
                bd=2,
            )
            value.place(x=18, y=82, width=309, height=230)

            if key == "air":
                left_unit = tk.Canvas(
                    outer, width=154, height=55, bg="white", highlightthickness=0
                )
                left_unit.place(x=18, y=322)
                left_unit.create_text(
                    154,
                    27,
                    text="PSI",
                    font=("Arial", 24, "bold"),
                    fill="black",
                )
                right_unit = tk.Canvas(
                    outer,
                    width=155,
                    height=55,
                    bg="#202020",
                    highlightthickness=0,
                )
                right_unit.place(x=172, y=322)
                right_unit.create_text(
                    0,
                    27,
                    text="PSI",
                    font=("Arial", 24, "bold"),
                    fill="white",
                )
            else:
                tk.Label(
                    outer,
                    text=unit,
                    font=("Arial", 24, "bold"),
                    bg=background,
                    fg=foreground,
                ).place(x=18, y=322, width=309, height=55)

            status = tk.Label(
                outer,
                text="OFFLINE",
                font=("Arial", 22, "bold"),
                bg=OFFLINE_BG,
                fg=OFFLINE_FG,
                relief="solid",
                bd=2,
            )
            status.place(x=18, y=397, width=309, height=70)
            self.detail_gases[key] = (value, status)

        self.detail_footer = tk.Label(
            self.detail_page,
            text="",
            font=("Arial", 12),
            bg=PAGE_BG,
        )
        self.detail_footer.pack(pady=15)

    def start_workers(self):
        for state in self.states.values():
            worker = PanelWorker(
                state,
                self.config["listen_port"],
                self.events,
                self.stop_event,
            )
            self.workers.append(worker)
            worker.start()

    def process_events(self):
        try:
            while True:
                event, panel_id, values = self.events.get_nowait()
                state = self.states[panel_id]
                if event == "connected":
                    state.error = ""
                elif event == "disconnected":
                    state.online = False
                    state.error = values.get("error", "Disconnected")
                elif event == "telemetry":
                    state.data = values["data"]
                    state.online = True
                    state.last_seen = time.monotonic()
                    state.error = ""
                self.refresh_panel(panel_id)
                self.refresh_visible_cards()
        except queue.Empty:
            pass

        self.root.after(100, self.process_events)

    def watchdog(self):
        now = time.monotonic()
        timeout = self.config["offline_seconds"]
        for panel_id, state in self.states.items():
            if state.online and now - state.last_seen > timeout:
                state.online = False
                state.error = "Telemetry timeout"
                self.refresh_panel(panel_id)

        self.refresh_visible_cards()

        online = sum(1 for state in self.states.values() if state.online)
        alarms = sum(
            1
            for state in self.states.values()
            if state.online and state.data.get("alarm_active", False)
        )
        self.summary.config(
            text=f"{online} CONNECTED  |  {alarms} ALARM"
        )
        self.root.after(1000, self.watchdog)

    def refresh_panel(self, panel_id):
        self.cards[panel_id].update()
        if self.current_detail_id == panel_id:
            self.update_detail()

    def refresh_visible_cards(self):
        online_ids = [
            panel_id
            for panel_id, state in self.states.items()
            if state.online
        ]

        if online_ids == self.visible_panel_ids:
            return

        self.visible_panel_ids = online_ids
        for card in self.cards.values():
            card.frame.grid_forget()
        self.empty_message.grid_forget()

        if not online_ids:
            self.empty_message.grid(row=0, column=0, padx=30, pady=80)
            return

        for index, panel_id in enumerate(online_ids):
            self.cards[panel_id].grid(index // 4, index % 4)

    def save_panel_names(self):
        for item in self.config["panels"]:
            item["name"] = self.states[item["id"]].name

        temporary_path = CONFIG_PATH.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(self.config, indent=2), encoding="utf-8"
        )
        temporary_path.replace(CONFIG_PATH)

    def edit_current_panel_name(self):
        if not self.current_detail_id:
            return

        state = self.states[self.current_detail_id]
        new_name = simpledialog.askstring(
            "Edit Panel Name",
            "Enter the panel name or location:",
            initialvalue=state.name,
            parent=self.root,
        )
        if new_name is None:
            return

        new_name = new_name.strip()
        if not new_name:
            messagebox.showerror(
                "Invalid Name", "Panel name cannot be empty.", parent=self.root
            )
            return

        state.name = new_name[:40]
        try:
            self.save_panel_names()
        except OSError as error:
            messagebox.showerror(
                "Save Failed", f"Could not save the panel name:\n{error}", parent=self.root
            )
            return

        self.cards[state.panel_id].update()
        self.update_detail()

    def show_overview(self):
        self.current_detail_id = None
        self.detail_page.pack_forget()
        self.overview_page.pack(fill="both", expand=True)

    def show_detail(self, panel_id):
        self.current_detail_id = panel_id
        self.overview_page.pack_forget()
        self.detail_page.pack(fill="both", expand=True)
        self.update_detail()

    def update_detail(self):
        if not self.current_detail_id:
            return

        state = self.states[self.current_detail_id]
        data = state.data
        self.detail_title.config(text=state.name)

        if state.online:
            alarm = bool(data.get("alarm_active", False))
            self.detail_connection.config(
                text="ALARM" if alarm else "ONLINE",
                bg=ALARM_BG if alarm else NORMAL_BG,
                fg=ALARM_FG if alarm else NORMAL_FG,
            )
        else:
            self.detail_connection.config(
                text="OFFLINE", bg=OFFLINE_BG, fg=OFFLINE_FG
            )

        for key, (value_widget, status_widget) in self.detail_gases.items():
            if not state.online:
                value_widget.config(text="--", fg=OFFLINE_FG)
                status_widget.config(
                    text="OFFLINE", bg=OFFLINE_BG, fg=OFFLINE_FG
                )
                continue

            alarm = bool(data.get(f"{key}_alarm", False))
            status = data.get(f"{key}_status", "LOW PRESSURE" if alarm else "NORMAL")
            value_widget.config(
                text=str(data.get(key, "--")),
                fg=ALARM_FG if alarm else "black",
            )
            status_widget.config(
                text=status,
                bg=ALARM_BG if alarm else NORMAL_BG,
                fg=ALARM_FG if alarm else NORMAL_FG,
            )

        last_seen = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if state.online
            else state.error
        )
        self.detail_footer.config(
            text=f"{state.ip}:{self.config['listen_port']}  |  {last_seen}"
        )

    def blink_alarms(self):
        self.blink_visible = not self.blink_visible

        for card in self.cards.values():
            card.apply_blink(self.blink_visible)

        if self.current_detail_id:
            state = self.states[self.current_detail_id]
            if state.online:
                data = state.data
                for key, (value_widget, status_widget) in self.detail_gases.items():
                    if data.get(f"{key}_alarm", False):
                        if self.blink_visible:
                            value_widget.config(fg=ALARM_FG)
                            status_widget.config(
                                bg=ALARM_BG,
                                fg=ALARM_FG,
                            )
                        else:
                            value_widget.config(fg="white")
                            status_widget.config(bg="white", fg="white")

                if data.get("alarm_active", False):
                    self.detail_connection.config(
                        bg=ALARM_BG if self.blink_visible else "white",
                        fg=ALARM_FG if self.blink_visible else "white",
                    )

        self.root.after(500, self.blink_alarms)

    def update_clock(self):
        self.clock.config(text=datetime.now().strftime("%A, %d %B %Y  %H:%M:%S"))
        self.root.after(1000, self.update_clock)

    def on_close(self):
        self.stop_event.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = DashboardApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
