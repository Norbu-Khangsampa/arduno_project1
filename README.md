# Arduino Motor Control

**A DC motor you can start, stop and speed-control from a physical button and
knob or from a phone or laptop, with an Arduino Uno running the motor, a
Raspberry Pi 5 as the gateway, and a firmware fail-safe that stops the motor
if the link to the Pi is lost.**

| | |
|---|---|
| **Measured result** | Stop-time test (20 trials): in progress, no results published yet |
| **Demo** | 90-second demo video: coming soon |
| **Main setup** | `firmware/motor_fsm` + `src/serial_bridge.py` + `src/mqtt_dashboard.py` |

### System diagram

```
 Browser dashboard         Raspberry Pi 5 (gateway, Python)    Arduino Uno R3 (edge, C)
┌──────────────────┐      ┌──────────────────────────────┐            ┌──────────────────────┐
│ on/off + slider  │ HTTP │ mqtt_dashboard.py (Flask)    │            │ 4-state machine:     │
│ polls /telemetry │◄────►│   │ motor/cmd    ▲ telemetry │            │ Off / Knob /         │
│ every 200 ms;    │      │   ▼              │           │            │ Web Override / Fault │
│ each poll → <H>  │      │ Mosquitto MQTT broker        │            │                      │
└──────────────────┘      │   │ motor/cmd    ▲ telemetry │            │ 2 s heartbeat        │
                          │   ▼              │           │ USB serial │ watchdog → lockout   │
                          │ serial_bridge.py             │◄──────────►│ fault → button reset │
                          └──────────────────────────────┘ 9600 baud  └──────────────────────┘
                                                                                  │ D9 PWM
                                                                                  ▼
                                                                 S8050 NPN (330 Ω base) → DC motor
                                                                 1N4007 flyback · button D2 · knob A0

 Down: <1,speed> · <0> · <H>       Up: <state,speed,pot> every 200 ms
```

The safety logic lives at the edge: if the heartbeat stops for 2,000 ms
(closed tab, stopped dashboard or bridge), the firmware stops the motor and
locks out until the physical button is pressed. Full wiring is in
[`docs/wiring.md`](docs/wiring.md).

### Status / Planned

**Built**
- 4-state firmware with the 2 s communication watchdog and fault lockout (`firmware/motor_fsm`)
- MQTT gateway: serial bridge and Flask dashboard, including a "simulate Wi-Fi drop" button that pauses the heartbeat to test the watchdog
- Earlier direct-serial version with a Web Worker heartbeat (`firmware/motor_serial` + `src/pi_motor_server.py`)

**In progress (not public yet)**
- Stop-time test, 20 trials
- 90-second demo video and breadboard photo

**Planned (not built)**
- Closed-loop speed control with an encoder motor and a PI loop

## Two setups

| Firmware | Pi side | Description |
|----------|---------|-------------|
| `firmware/motor_serial` | `src/pi_motor_server.py` | Flask dashboard talking to the Arduino directly over USB serial. The browser sends heartbeats, and the motor stops about 2 s after the page closes. |
| `firmware/motor_fsm` | `src/serial_bridge.py` + `src/mqtt_dashboard.py` | Explicit 4-state machine (Off / Knob / Web Override / Fault Lockout). Commands and telemetry go through a Mosquitto MQTT broker. If heartbeats are lost the motor locks out until the physical button is pressed. |

`src/iot_node.py` is a separate minimal example: it toggles an LED and reads a
button on the Pi's own GPIO from a web page.

## Project structure

```
arduno_project1/
├── firmware/
│   ├── motor_fsm/motor_fsm.ino        4-state FSM + watchdog (MQTT setup)
│   └── motor_serial/motor_serial.ino  direct-serial controller
├── src/
│   ├── pi_motor_server.py   direct-serial web dashboard
│   ├── serial_bridge.py     USB serial <-> MQTT bridge
│   ├── mqtt_dashboard.py    MQTT web dashboard
│   └── iot_node.py          Pi GPIO LED/button web demo
├── tools/
│   ├── serial_monitor.py    raw serial smoke test
│   └── gpio_button_test.py  Pi LED/button wiring check
├── docs/
│   └── wiring.md            schematic, pin tables and serial protocol
└── requirements.txt
```

## Hardware

- Arduino Uno R3 (or compatible), connected to the Pi by USB
- Small DC motor with its own power supply
- S8050 NPN transistor with a 330 Ω base resistor
- 1N4007 flyback diode and a 10 µF decoupling capacitor
- 10 kΩ potentiometer and a momentary push button
- Raspberry Pi 5

| Arduino pin | Connects to |
|-------------|-------------|
| D2 | Push button to GND (internal pull-up) |
| A0 | Potentiometer wiper |
| D9 (PWM) | S8050 base through 330 Ω |
| USB | Raspberry Pi 5 |

| Pi 5 GPIO | Header pin | Connects to (iot_node / gpio_button_test) |
|-----------|------------|-------------------------------------------|
| GPIO 22 | Pin 15 | LED + 330 Ω resistor to GND |
| GPIO 17 | Pin 11 | Push button to GND (internal pull-up) |

The motor needs its own supply, a flyback diode across its terminals, and a
ground shared with the Arduino. See [`docs/wiring.md`](docs/wiring.md) for the
schematic and the full serial protocol.

## Quickstart

**1. Flash the firmware.** Open `firmware/motor_serial/motor_serial.ino` or
`firmware/motor_fsm/motor_fsm.ino` in the Arduino IDE, select *Arduino Uno*,
and upload.

**2. Install the Pi dependencies.**

```bash
sudo apt install -y python3-flask python3-serial python3-paho-mqtt mosquitto
sudo usermod -aG dialout $USER     # serial port access; log out and back in
```

**3a. Direct-serial dashboard** (with `motor_serial` firmware):

```bash
python3 src/pi_motor_server.py                  # defaults to /dev/ttyACM0
python3 src/pi_motor_server.py --port COM5      # when run from a Windows PC
```

**3b. MQTT dashboard** (with `motor_fsm` firmware):

```bash
sudo systemctl enable --now mosquitto
python3 src/serial_bridge.py &
python3 src/mqtt_dashboard.py
```

Then open `http://<pi-hostname>.local:5000` from any device on the same
network.

## Configuration

Nothing network-specific is hardcoded. Defaults can be overridden with
environment variables:

| Variable | Default | Used by |
|----------|---------|---------|
| `SERIAL_PORT` | `/dev/ttyACM0` | `pi_motor_server.py`, `serial_bridge.py` |
| `MQTT_BROKER` | `localhost` | `serial_bridge.py`, `mqtt_dashboard.py` |
| `MQTT_PORT` | `1883` | `serial_bridge.py`, `mqtt_dashboard.py` |
| `DASHBOARD_HOST` | `0.0.0.0` | all dashboards |
| `DASHBOARD_PORT` | `5000` | all dashboards |

## Serial protocol

Packets are framed with `<` and `>` and end with a newline.

| Direction | Packet | Meaning |
|-----------|--------|---------|
| Pi → Arduino | `<1,180>` | Motor on at PWM 180 (web override) |
| Pi → Arduino | `<1>` / `<0>` | Motor on at current speed / off |
| Pi → Arduino | `<H>` | Heartbeat; must arrive at least every 2 s during web override |
| Pi → Arduino | `<X>` | Server shutting down (motor_serial only) |
| Arduino → Pi | `<state,speed,pot>` | Telemetry every 200 ms |

## Tools

- `tools/serial_monitor.py` finds the Arduino, prints its raw output, and
  sends a test packet. Use `--port` and `--command` to override.
- `tools/gpio_button_test.py`: the LED on GPIO 22 lights while the button on
  GPIO 17 is held.

## Security note

The dashboards have no authentication and listen on all interfaces by
default. Run them only on a trusted local network, or set
`DASHBOARD_HOST=127.0.0.1` and reach them through an SSH tunnel.
