# Arduino Motor Control – Wiring

## Parts

| Part | Notes |
|------|-------|
| Arduino Uno R3 (or Elegoo Uno R3) | Connected to the Pi by USB (`/dev/ttyACM0`) |
| Small DC motor | Powered from its own supply, not the Arduino 5 V pin |
| Logic-level N-channel MOSFET (e.g. IRLZ44N) or NPN transistor (TIP120) | Switches the motor from PWM pin D9 |
| Flyback diode (1N4007 / 1N5819) | Across the motor terminals |
| 10 kΩ potentiometer | Speed knob |
| Momentary push button | On/off and fault reset |
| Raspberry Pi 5 | Runs the web dashboards and the MQTT broker |

## Arduino Uno

| Arduino pin | Connects to |
|-------------|-------------|
| D2 | Push button → GND (uses the internal pull-up, so no resistor needed) |
| A0 | Potentiometer wiper (middle leg); outer legs to 5 V and GND |
| D9 (PWM) | MOSFET gate through a 220 Ω resistor; 10 kΩ from gate to GND |
| GND | MOSFET source, motor supply GND, pot GND, button GND |
| USB | Raspberry Pi USB port (power + serial at 9600 baud) |

```
 Motor supply (+) ──────────┬──────────────┐
                            │              │
                          Motor       Flyback diode
                            │         (stripe to +)
                            ├──────────────┘
                            │
                     MOSFET drain
 D9 ──220Ω── gate          │
         │            MOSFET source
        10k                 │
         │                  │
 GND ────┴──────────────────┴──── Motor supply (−) ── Arduino GND
```

**Common ground is essential:** the motor supply's negative terminal must be
tied to the Arduino GND, or the MOSFET will not switch reliably.

## Raspberry Pi 5 GPIO (iot_node.py / gpio_button_test.py)

| Component | GPIO | Header pin | Used by |
|-----------|------|------------|---------|
| LED (+ 330 Ω resistor to GND) | GPIO 22 | Pin 15 | `src/iot_node.py`, `tools/gpio_button_test.py` |
| Push button → GND | GPIO 17 | Pin 11 | `src/iot_node.py`, `tools/gpio_button_test.py` (internal pull-up) |

## Serial protocol

Packets are framed with `<` and `>` and end with a newline.

| Direction | Packet | Meaning |
|-----------|--------|---------|
| Pi → Arduino | `<1,180>` | Motor on at PWM 180 (web override) |
| Pi → Arduino | `<1>` / `<0>` | Motor on at current speed / off |
| Pi → Arduino | `<H>` | Heartbeat; must arrive at least every 2 s during web override |
| Pi → Arduino | `<X>` | Server shutting down (motor_serial only) |
| Arduino → Pi | `<state,speed,pot>` | Telemetry every 200 ms |

`motor_fsm` reports `state` as 0 = off, 1 = knob control, 2 = web override,
3 = watchdog fault lockout (press the button to clear).
