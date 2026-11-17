"""Minimal IoT node: toggle an LED and read a button on the Pi 5 from a web page."""

import os
import socket

import lgpio
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# --- 1. Low-Level Hardware Setup (Bypassing gpiozero) ---
LED_PIN = 22
BUTTON_PIN = 17


def open_header_gpiochip():
    """Open the gpiochip that drives the 40-pin header (the RP1 on a Pi 5).

    Older Pi 5 kernels exposed it as gpiochip4, newer ones as gpiochip0,
    so look it up by label rather than hardcoding the number.
    """
    for chip in (0, 4, 1, 2, 3):
        try:
            h = lgpio.gpiochip_open(chip)
        except lgpio.error:
            continue
        _, _, _, label = lgpio.gpio_get_chip_info(h)
        if label == "pinctrl-rp1":
            return h
        lgpio.gpiochip_close(h)
    return lgpio.gpiochip_open(0)  # older Pi models


# Open the hardware connection
handle = open_header_gpiochip()

# Configure the LED as an Output and set it LOW (off)
lgpio.gpio_claim_output(handle, LED_PIN)
lgpio.gpio_write(handle, LED_PIN, 0)
led_state = False

# Configure the Button as an Input with a Pull-Up resistor
lgpio.gpio_claim_input(handle, BUTTON_PIN, lgpio.SET_PULL_UP)

# --- 2. Embedded Web Dashboard ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Pi IoT Dashboard</title>
    <style>
        body { font-family: -apple-system, sans-serif; text-align: center; margin-top: 50px; background: #f4f4f9; color: #333; }
        .card { background: white; padding: 20px; border-radius: 10px; margin: 20px auto; max-width: 400px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        button { font-size: 18px; padding: 12px 24px; cursor: pointer; background: #007bff; color: white; border: none; border-radius: 5px; }
        button:active { background: #0056b3; }
        .status { font-size: 24px; font-weight: bold; margin: 15px; }
        .alert { color: #dc3545; }
        .clear { color: #28a745; }
    </style>
</head>
<body>
    <h1>Project TelemetryNode</h1>
    
    <div class="card">
        <h2>Remote Actuation</h2>
        <p>Control the physical LED from the web.</p>
        <button onclick="toggleLED()">Toggle LED</button>
    </div>

    <div class="card">
        <h2>Live Telemetry</h2>
        <p>Physical button state:</p>
        <div class="status" id="sensor-state">Checking...</div>
    </div>

    <script>
        function toggleLED() {
            fetch('/api/toggle', { method: 'POST' });
        }

        setInterval(function() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    let stateElement = document.getElementById('sensor-state');
                    if (data.button_pressed) {
                        stateElement.innerHTML = "<span class='alert'>🚨 BUTTON PRESSED</span>";
                    } else {
                        stateElement.innerHTML = "<span class='clear'>✅ Clear</span>";
                    }
                });
        }, 200);
    </script>
</body>
</html>
"""

# --- 3. Web Routes ---
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def get_status():
    # lgpio returns 0 when a pull-up button is pressed
    is_pressed = (lgpio.gpio_read(handle, BUTTON_PIN) == 0)
    return jsonify({"button_pressed": is_pressed})

@app.route('/api/toggle', methods=['POST'])
def toggle_led():
    global led_state
    led_state = not led_state
    # Write 1 for ON, 0 for OFF
    lgpio.gpio_write(handle, LED_PIN, 1 if led_state else 0)
    return jsonify({"success": True})

if __name__ == '__main__':
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    shown_host = socket.gethostname() + ".local" if host == "0.0.0.0" else host
    print(f"Dashboard: http://{shown_host}:{port}")
    try:
        app.run(host=host, port=port)
    finally:
        # Clean up the hardware connection when the server stops
        lgpio.gpiochip_close(handle)
