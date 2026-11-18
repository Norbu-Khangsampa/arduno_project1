# Arduino Motor Control – Wiring

## Parts

| Part | Notes |
|------|-------|
| Arduino Uno R3 (or Elegoo Uno R3) | Connected to the Pi by USB (`/dev/ttyACM0`) |
| Small DC motor | Powered from its own supply, not the Arduino 5 V pin |
| S8050 NPN transistor | Low-side switch for the motor, driven from PWM pin D9 |
| 330 Ω resistor | Base resistor between D9 and the S8050 base |
| 1N4007 flyback diode | Across the motor terminals |
| 10 µF capacitor | Decoupling |
| 10 kΩ potentiometer | Speed knob |
| Momentary push button | On/off and fault reset |
| Raspberry Pi 5 | Runs the web dashboards and the MQTT broker |

## Arduino Uno

| Arduino pin | Connects to |
|-------------|-------------|
| D2 | Push button → GND (uses the internal pull-up, so no resistor needed) |
| A0 | Potentiometer wiper (middle leg); outer legs to 5 V and GND |
| D9 (PWM) | S8050 base through a 330 Ω resistor |
| GND | S8050 emitter, motor supply GND, pot GND, button GND |
| USB | Raspberry Pi USB port (power + serial at 9600 baud) |

```
 Motor supply (+) ──────────┬──────────────┐
                            │              │
                          Motor       Flyback diode
                            │         (stripe to +)
                            ├──────────────┘
                            │
                      S8050 collector
 D9 ──330Ω── base           │
                      S8050 emitter
                            │
 GND ───────────────────────┴──── Motor supply (−) ── Arduino GND
```

**Common ground is essential:** the motor supply's negative terminal must be
tied to the Arduino GND, or the transistor will not switch reliably.

Keep the motor's stall current inside the S8050's collector-current rating.

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
