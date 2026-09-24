"""Panel firmware for the scalable medical-gas alarm.

Target hardware:
  Raspberry Pi Pico W running MicroPython
  W5500 Ethernet module on SPI1
  TJC8048X350_01R display on UART0
  Three analogue pressure sensors on ADC0..ADC2

The local display, alarm and buzzer do not depend on the Ethernet connection.
Ethernet telemetry is sent to the Windows dashboard by a background thread.
"""

from machine import ADC, Pin, SPI, UART
import _thread
import json
import time

try:
    import network
except ImportError:
    # Keep the medical-gas alarm operating locally even if the installed
    # MicroPython build does not contain the optional WIZnet network driver.
    network = None

try:
    import socket
except ImportError:
    try:
        import usocket as socket
    except ImportError:
        socket = None


# =========================================================
# PANEL CONFIGURATION
# =========================================================

CONFIG_FILE = "panel_config.json"
FIRMWARE_VERSION = "panel-ethernet-1.1"

DEFAULT_CONFIG = {
    "panel_id": "panel-01",
    "panel_name": "Panel 01",
    "panel_ip": "192.168.10.101",
    "subnet_mask": "255.255.255.0",
    "gateway": "192.168.10.1",
    "dns": "192.168.10.1",
    "server_ip": "192.168.10.1",
    "server_port": 5050,
}


def load_panel_config():
    config = DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as file:
            saved = json.loads(file.read())

        for key in config:
            if key in saved:
                config[key] = saved[key]

        print("DEBUG:Panel configuration loaded")
    except Exception as error:
        print("DEBUG:Using default panel configuration: {}".format(error))

    config["server_port"] = int(config["server_port"])
    return config


panel_config = load_panel_config()


# =========================================================
# HARDWARE
# =========================================================

# Analogue pressure sensors (confirmed panel wiring)
air_sensor = ADC(Pin(26))       # ADC0, Air 4 Bar, PSI
oxygen_sensor = ADC(Pin(27))    # ADC1, Oxygen, PSI
vacuum_sensor = ADC(Pin(28))    # ADC2, Vacuum, mmHg

buzzer = Pin(16, Pin.OUT)
buzzer.value(0)

# Pico GP0 TX -> TJC RX, Pico GP1 RX <- TJC TX
uart = UART(0, baudrate=9600, tx=Pin(0), rx=Pin(1))

# W5500 on SPI1
w5500_spi = SPI(
    1,
    baudrate=2_000_000,
    polarity=0,
    phase=0,
    sck=Pin(10),
    mosi=Pin(11),
    miso=Pin(12),
)
w5500_cs = Pin(13, Pin.OUT, value=1)
w5500_reset = Pin(14, Pin.OUT, value=1)
w5500_interrupt = Pin(15, Pin.IN, Pin.PULL_UP)


# =========================================================
# SENSOR AND ALARM SETTINGS
# =========================================================

ADC_MAX = 65535
ADC_REF = 3.3
SAMPLES = 10

# Oxygen and air states:
# Below 30 PSI = LOW, 30..90 PSI = NORMAL, above 90 PSI = HIGH.
OXYGEN_LOW_LIMIT = 30
OXYGEN_HIGH_LIMIT = 90
AIR_LOW_LIMIT = 30
AIR_HIGH_LIMIT = 90
# Vacuum: -250 mmHg through 0 = LOW; below -250 mmHg = NORMAL.
# There is no HIGH PRESSURE state for vacuum.
VACUUM_ALARM_LIMIT = -250

SENSOR_UPDATE_INTERVAL_MS = 1000
USB_UPDATE_INTERVAL_MS = 1000
BUZZER_INTERVAL_MS = 300

TEST_TARGET_OXYGEN = 52
TEST_TARGET_AIR = 52
TEST_TARGET_VACUUM = -375
TEST_STEP = 5
TEST_INTERVAL_MS = 300

TELEMETRY_INTERVAL_MS = 1000
NETWORK_RETRY_INTERVAL_MS = 5000
NETWORK_SOCKET_TIMEOUT_SECONDS = 2


# =========================================================
# SYSTEM STATE
# =========================================================

muted = False
alarm_active = False
test_active = False

buzzer_on = False
last_buzzer_time = 0
last_sensor_update = 0
last_usb_update = 0

uart_buffer = ""

test_oxygen = 0
test_air = 0
test_vacuum = 0
last_test_update = 0

current_oxygen = 0
current_air = 0
current_vacuum = 0

current_oxygen_alarm = False
current_air_alarm = False
current_vacuum_alarm = False
current_oxygen_status = "LOW PRESSURE"
current_air_status = "LOW PRESSURE"
current_vacuum_status = "LOW PRESSURE"

ethernet_ready = False
ethernet_link = False
server_connected = False
network_last_error = "Ethernet starting"

last_usb_line = ""
state_lock = _thread.allocate_lock()
displayed_network_state = None


def debug(message):
    try:
        print("DEBUG:" + str(message))
    except Exception:
        pass


# =========================================================
# TJC LCD FUNCTIONS
# =========================================================

def send_tjc(command):
    try:
        uart.write(command.encode())
        uart.write(b"\xff\xff\xff")
        time.sleep_ms(50)
    except Exception as error:
        debug("TJC write error: {}".format(error))


def set_text(name, text):
    send_tjc('{}.txt="{}"'.format(name, text))


def set_val(name, value):
    send_tjc("{}.val={}".format(name, value))


def set_status_colors(name, is_alarm):
    if is_alarm:
        send_tjc("{}.bco=64560".format(name))
        send_tjc("{}.pco=51200".format(name))
    else:
        send_tjc("{}.bco=51192".format(name))
        send_tjc("{}.pco=736".format(name))


def update_muted_icon():
    # bMute is a TJC dual-state picture button: 0=MUTE action, 1=UNMUTE action.
    set_val("bMute", 1 if muted else 0)


def update_ethernet_icon():
    # The existing HMI uses pWifi. The recreated HMI can rename this to an
    # Ethernet icon while retaining the same component name for compatibility.
    send_tjc("vis pWifi,{}".format(1 if server_connected else 0))


def refresh_ethernet_icon():
    """Write to the shared TJC UART from the main thread only."""
    global displayed_network_state

    if displayed_network_state != server_connected:
        displayed_network_state = server_connected
        update_ethernet_icon()


# =========================================================
# SENSOR CONVERSION
# =========================================================

def read_voltage(adc):
    total = 0
    for _ in range(SAMPLES):
        total += adc.read_u16()
        time.sleep_ms(1)
    return (total / SAMPLES / ADC_MAX) * ADC_REF


def map_value(value, in_min, in_max, out_min, out_max):
    return out_min + (
        (value - in_min) * (out_max - out_min) / (in_max - in_min)
    )


def vacuum_voltage_to_mmhg(voltage):
    if voltage >= 0.4390:
        value = 0
    elif voltage >= 0.4045:
        value = map_value(voltage, 0.4390, 0.4045, 0, -125)
    elif voltage >= 0.3450:
        value = map_value(voltage, 0.4045, 0.3450, -125, -250)
    else:
        value = map_value(voltage, 0.3450, 0.2920, -250, -375)

    return round(max(-375, min(0, value)))


def oxygen_voltage_to_psi(voltage):
    if voltage <= 0.4846:
        value = 0
    elif voltage <= 0.9691:
        value = map_value(voltage, 0.4846, 0.9691, 0, 25)
    elif voltage <= 1.5319:
        value = map_value(voltage, 0.9691, 1.5319, 25, 50)
    else:
        value = map_value(voltage, 1.5319, 2.0644, 50, 75)

    value = max(0, value)
    if value < 7:
        value = 0
    return round(value)


def air_voltage_to_psi(voltage):
    if voltage <= 0.4973:
        value = 0
    elif voltage <= 0.9816:
        value = map_value(voltage, 0.4973, 0.9816, 0, 25)
    elif voltage <= 1.5488:
        value = map_value(voltage, 0.9816, 1.5488, 25, 50)
    else:
        value = map_value(voltage, 1.5488, 2.0826, 50, 75)

    value = max(0, value)
    if value < 7:
        value = 0
    return round(value)


# =========================================================
# DISPLAY AND STATE
# =========================================================

def pressure_status(value, low_limit, high_limit):
    if value < low_limit:
        return "LOW PRESSURE"
    if value > high_limit:
        return "HIGH PRESSURE"
    return "NORMAL"


def update_status(status_component, alarm_variable, status):
    is_alarm = status != "NORMAL"
    set_text(status_component, status)
    set_status_colors(status_component, is_alarm)
    set_val(alarm_variable, 1 if is_alarm else 0)


def show_values(oxygen, air, vacuum):
    global alarm_active
    global current_oxygen, current_air, current_vacuum
    global current_oxygen_alarm, current_air_alarm, current_vacuum_alarm
    global current_oxygen_status, current_air_status, current_vacuum_status

    oxygen_status = pressure_status(
        oxygen, OXYGEN_LOW_LIMIT, OXYGEN_HIGH_LIMIT
    )
    air_status = pressure_status(air, AIR_LOW_LIMIT, AIR_HIGH_LIMIT)
    vacuum_status = (
        "LOW PRESSURE" if vacuum >= VACUUM_ALARM_LIMIT else "NORMAL"
    )

    oxygen_alarm = oxygen_status != "NORMAL"
    air_alarm = air_status != "NORMAL"
    vacuum_alarm = vacuum >= VACUUM_ALARM_LIMIT

    state_lock.acquire()
    current_oxygen = oxygen
    current_air = air
    current_vacuum = vacuum
    current_oxygen_alarm = oxygen_alarm
    current_air_alarm = air_alarm
    current_vacuum_alarm = vacuum_alarm
    current_oxygen_status = oxygen_status
    current_air_status = air_status
    current_vacuum_status = vacuum_status
    alarm_active = oxygen_alarm or air_alarm or vacuum_alarm
    state_lock.release()

    set_text("tOxygen", str(oxygen))
    set_text("tAir", str(air))
    set_text("tVacuum", str(vacuum))

    update_status("tOxygenStatus", "vaOxygenAlarm", oxygen_status)
    update_status("tAirStatus", "vaAirAlarm", air_status)
    update_status("tVacuumStatus", "vaVacuumAlarm", vacuum_status)


def update_sensor_display():
    oxygen = oxygen_voltage_to_psi(read_voltage(oxygen_sensor))
    air = air_voltage_to_psi(read_voltage(air_sensor))
    vacuum = vacuum_voltage_to_mmhg(read_voltage(vacuum_sensor))
    show_values(oxygen, air, vacuum)


def telemetry_data():
    state_lock.acquire()
    data = {
        "type": "telemetry",
        "protocol_version": 1,
        "firmware_version": FIRMWARE_VERSION,
        "panel_id": panel_config["panel_id"],
        "panel_name": panel_config["panel_name"],
        "panel_ip": panel_config["panel_ip"],
        "oxygen": current_oxygen,
        "air": current_air,
        "vacuum": current_vacuum,
        "oxygen_alarm": current_oxygen_alarm,
        "air_alarm": current_air_alarm,
        "vacuum_alarm": current_vacuum_alarm,
        "oxygen_status": current_oxygen_status,
        "air_status": current_air_status,
        "vacuum_status": current_vacuum_status,
        "alarm_active": alarm_active,
        "muted": muted,
        "test_active": test_active,
        "ethernet_link": ethernet_link,
        "server_connected": server_connected,
        "network_error": network_last_error,
        "uptime_ms": time.ticks_ms(),
    }
    state_lock.release()
    return data


def send_usb_json(force=False):
    global last_usb_line
    line = json.dumps(telemetry_data())
    if force or line != last_usb_line:
        print(line)
        last_usb_line = line


# =========================================================
# BUZZER
# =========================================================

def update_buzzer():
    global buzzer_on, last_buzzer_time

    if muted or not (alarm_active or test_active):
        buzzer.value(0)
        buzzer_on = False
        return

    now = time.ticks_ms()
    if time.ticks_diff(now, last_buzzer_time) >= BUZZER_INTERVAL_MS:
        buzzer_on = not buzzer_on
        buzzer.value(1 if buzzer_on else 0)
        last_buzzer_time = now


# =========================================================
# LOCAL TEST FUNCTION
# =========================================================

def start_test():
    global test_active, test_oxygen, test_air, test_vacuum, last_test_update

    if test_active:
        return

    test_active = True
    test_oxygen = 0
    test_air = 0
    test_vacuum = 0
    last_test_update = time.ticks_ms()
    set_val("bTest", 1)
    show_values(test_oxygen, test_air, test_vacuum)
    send_usb_json(force=True)


def move_to_target(current, target):
    if current < target:
        return min(current + TEST_STEP, target)
    if current > target:
        return max(current - TEST_STEP, target)
    return current


def update_test():
    global test_active, test_oxygen, test_air, test_vacuum
    global last_test_update, last_sensor_update

    if not test_active:
        return

    now = time.ticks_ms()
    if time.ticks_diff(now, last_test_update) < TEST_INTERVAL_MS:
        return

    last_test_update = now
    test_oxygen = move_to_target(test_oxygen, TEST_TARGET_OXYGEN)
    test_air = move_to_target(test_air, TEST_TARGET_AIR)
    test_vacuum = move_to_target(test_vacuum, TEST_TARGET_VACUUM)
    show_values(test_oxygen, test_air, test_vacuum)
    send_usb_json(force=True)

    if (
        test_oxygen == TEST_TARGET_OXYGEN
        and test_air == TEST_TARGET_AIR
        and test_vacuum == TEST_TARGET_VACUUM
    ):
        test_active = False
        set_val("bTest", 0)
        update_sensor_display()
        send_usb_json(force=True)
        last_sensor_update = time.ticks_ms()


# =========================================================
# TJC COMMAND INPUT
# =========================================================

def process_lcd_command(command):
    global muted

    command = command.strip()
    if command == "MUTE_ON":
        muted = True
        buzzer.value(0)
        update_muted_icon()
        send_usb_json(force=True)
    elif command == "MUTE_OFF":
        muted = False
        update_muted_icon()
        send_usb_json(force=True)
    elif command == "TEST_START":
        start_test()


def read_lcd_commands():
    global uart_buffer

    if not uart.any():
        return

    data = uart.read()
    if not data:
        return

    for byte in data:
        if byte == 10:
            command = uart_buffer.strip()
            uart_buffer = ""
            if command in ("MUTE_ON", "MUTE_OFF", "TEST_START"):
                process_lcd_command(command)
        elif 32 <= byte <= 126:
            uart_buffer += chr(byte)

    if len(uart_buffer) > 40:
        uart_buffer = ""


# =========================================================
# W5500 ETHERNET AND DASHBOARD CONNECTION
# =========================================================

def set_network_status(ready=None, link=None, connected=None, error=None):
    global ethernet_ready, ethernet_link, server_connected, network_last_error

    state_lock.acquire()
    if ready is not None:
        ethernet_ready = ready
    if link is not None:
        ethernet_link = link
    if connected is not None:
        server_connected = connected
    if error is not None:
        network_last_error = error
    state_lock.release()


def close_socket(sock):
    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass


def send_all(sock, data):
    view = memoryview(data)
    sent = 0
    while sent < len(data):
        count = sock.send(view[sent:])
        if not count:
            raise OSError("Dashboard socket closed")
        sent += count


def ethernet_worker():
    nic = None
    listener = None
    dashboard_socket = None

    while True:
        try:
            if nic is None:
                debug("Starting W5500 Ethernet")
                nic = network.WIZNET5K(w5500_spi, w5500_cs, w5500_reset)
                nic.active(True)
                nic.ifconfig((
                    panel_config["panel_ip"],
                    panel_config["subnet_mask"],
                    panel_config["gateway"],
                    panel_config["dns"],
                ))
                set_network_status(ready=True, error="")
                debug("W5500 IP: {}".format(nic.ifconfig()))

            link_up = bool(nic.isconnected())
            set_network_status(link=link_up)

            if not link_up:
                close_socket(dashboard_socket)
                dashboard_socket = None
                close_socket(listener)
                listener = None
                set_network_status(connected=False, error="Ethernet cable disconnected")
                time.sleep_ms(NETWORK_RETRY_INTERVAL_MS)
                continue

            if listener is None:
                listener = socket.socket()
                try:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                except Exception:
                    pass
                listener.bind(("0.0.0.0", panel_config["server_port"]))
                listener.listen(1)
                listener.settimeout(1)
                set_network_status(error="Waiting for dashboard")
                debug("Panel telemetry server listening on port {}".format(
                    panel_config["server_port"]
                ))

            if dashboard_socket is None:
                try:
                    dashboard_socket, dashboard_address = listener.accept()
                except OSError:
                    # A one-second accept timeout is normal while the dashboard
                    # is closed. It also lets us keep checking the cable state.
                    continue

                dashboard_socket.settimeout(NETWORK_SOCKET_TIMEOUT_SECONDS)
                set_network_status(connected=True, error="")
                debug("Dashboard connected from {}".format(dashboard_address[0]))

            payload = (json.dumps(telemetry_data()) + "\n").encode()
            send_all(dashboard_socket, payload)
            time.sleep_ms(TELEMETRY_INTERVAL_MS)

        except Exception as error:
            close_socket(dashboard_socket)
            dashboard_socket = None
            close_socket(listener)
            listener = None
            set_network_status(connected=False, error=str(error))
            debug("Ethernet server error: {}".format(error))
            time.sleep_ms(NETWORK_RETRY_INTERVAL_MS)

# =========================================================
# MAIN
# =========================================================

time.sleep(6)

send_tjc("tmBlink.en=1")
update_muted_icon()
update_ethernet_icon()

# Clear stale TJC UART data.
while uart.any():
    uart.read()
    time.sleep_ms(20)

update_sensor_display()
send_usb_json(force=True)

last_sensor_update = time.ticks_ms()
last_usb_update = time.ticks_ms()
last_buzzer_time = time.ticks_ms()

if network is None:
    set_network_status(
        error="MicroPython network module is unavailable"
    )
    debug(network_last_error)
elif socket is None:
    set_network_status(error="MicroPython socket/usocket module is unavailable")
    debug(network_last_error)
else:
    try:
        _thread.start_new_thread(ethernet_worker, ())
    except Exception as error:
        set_network_status(error="Ethernet thread failed: {}".format(error))
        debug(network_last_error)

while True:
    read_lcd_commands()
    refresh_ethernet_icon()

    if test_active:
        update_test()
    else:
        now = time.ticks_ms()

        if time.ticks_diff(now, last_sensor_update) >= SENSOR_UPDATE_INTERVAL_MS:
            last_sensor_update = now
            update_sensor_display()

        if time.ticks_diff(now, last_usb_update) >= USB_UPDATE_INTERVAL_MS:
            last_usb_update = now
            send_usb_json()

    update_buzzer()
    time.sleep_ms(20)
