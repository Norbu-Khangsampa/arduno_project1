"""Web dashboard for the 4-state motor FSM, talking to the Arduino over MQTT.

Run serial_bridge.py alongside this so MQTT messages reach the Arduino.

Settings come from environment variables:
    MQTT_BROKER     (default localhost)
    MQTT_PORT       (default 1883)
    DASHBOARD_HOST  (default 0.0.0.0)
    DASHBOARD_PORT  (default 5000)
"""

import os
import socket

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, request, render_template_string

MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
DASHBOARD_HOST = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "5000"))


def make_mqtt_client():
    """Create a client that works with both paho-mqtt 1.x and 2.x."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:  # paho-mqtt < 2.0
        return mqtt.Client()

# Shared dictionary holding the latest telemetry received from MQTT
telemetry = {"state": 0, "speed": 0, "pot": 0}

# --- 1. MQTT CALLBACK: Updates dictionary whenever "motor/telemetry" arrives ---
def on_message(client, userdata, msg):
    line = msg.payload.decode('utf-8', errors='ignore').strip()
    if line.startswith("<") and line.endswith(">"):
        parts = line[1:-1].split(",")
        if len(parts) == 3:
            telemetry["state"] = int(parts[0])
            telemetry["speed"] = int(parts[1])
            telemetry["pot"]   = int(parts[2])

mqtt_client = make_mqtt_client()
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.subscribe("motor/telemetry")
mqtt_client.loop_start()

# --- 2. FLASK WEB SERVER & 4-STATE DASHBOARD UI ---
app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <title>Pi 5 FSM Motor Control</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial, sans-serif; background: #121212; color: #fff; text-align: center; padding: 20px; }
    .card { background: #1e1e1e; border-radius: 12px; padding: 25px; max-width: 500px; margin: auto; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .badge { background: #0277bd; color: #e1f5fe; padding: 5px 12px; border-radius: 15px; font-size: 13px; display: inline-block; margin-bottom: 10px; }
    .status { font-size: 20px; font-weight: bold; margin: 15px 0; padding: 14px; border-radius: 8px; transition: 0.2s; }
    
    /* 4 Distinct FSM State Styles */
    .state-0 { background: #424242; color: #e0e0e0; } /* IDLE / MANUAL OFF */
    .state-1 { background: #1b5e20; color: #a5d6a7; } /* LOCAL KNOB ON */
    .state-2 { background: #0d47a1; color: #90caf9; } /* WEB OVERRIDE */
    .state-3 { background: #b71c1c; color: #ffcdd2; border: 2px solid #ff5252; animation: pulse 1s infinite; } /* FAULT LOCKOUT */

    @keyframes pulse {
      0% { opacity: 1; }
      50% { opacity: 0.65; }
      100% { opacity: 1; }
    }

    .metric { font-size: 18px; margin: 12px 0; background: #2c2c2c; padding: 12px; border-radius: 8px; }
    button { font-size: 16px; padding: 12px 20px; margin: 6px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
    .btn-on { background: #4caf50; color: white; }
    .btn-off { background: #f44336; color: white; }
    .btn-fault { background: #ff9800; color: #000; font-size: 14px; margin-top: 12px; }
    input[type=range] { width: 85%; margin: 15px 0; cursor: pointer; }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">🔗 4-State FSM + Mosquitto MQTT</div>
    <h2>📡 Industrial IoT Motor Center</h2>
    
    <div id="stateBox" class="status state-0">IDLE / MANUAL OFF (0)</div>
    
    <div class="metric">Active PWM Speed (0-255): <strong id="speedVal">0</strong></div>
    <div class="metric">Physical Knob ADC (0-1023): <strong id="potVal">0</strong></div>
    
    <hr style="border-color:#333; margin: 20px 0;">
    <h3>MQTT Web Override</h3>
    <button class="btn-on" onclick="sendCmd(1, document.getElementById('slider').value)">TURN ON (WEB)</button>
    <button class="btn-off" onclick="sendOff()">TURN OFF</button>
    <br><br>
    <label>Set Remote PWM Speed: <strong id="sliderLabel">180</strong></label><br>
    <input type="range" id="slider" min="0" max="255" value="180" 
           onmousedown="isDragging = true"
           ontouchstart="isDragging = true"
           oninput="handleSliderDrag(this.value)"
           onchange="finishSliderDrag(this.value)">
    <br>
    <button class="btn-fault" onclick="simulateDrop()">⚡ Simulate 3s Wi-Fi Drop (Test Watchdog Lockout)</button>
  </div>

  <script>
    let isDragging = false;
    let lastSliderMoveTime = 0;
    let pauseHeartbeatUntil = 0;

    function sendCmd(state, speed) {
      lastSliderMoveTime = Date.now();
      fetch(`/cmd?state=${state}&speed=${speed}`, { method: 'POST' });
    }

    function sendOff() {
      lastSliderMoveTime = Date.now();
      fetch(`/cmd?state=0`, { method: 'POST' });
    }

    function simulateDrop() {
      pauseHeartbeatUntil = Date.now() + 3000; // Pause <H> heartbeats for 3 seconds
    }

    function handleSliderDrag(val) {
      isDragging = true;
      lastSliderMoveTime = Date.now();
      document.getElementById('sliderLabel').innerText = val;
    }

    function finishSliderDrag(val) {
      isDragging = false;
      lastSliderMoveTime = Date.now();
      sendCmd(1, val);
    }

    setInterval(async () => {
      const dropActive = Date.now() < pauseHeartbeatUntil ? 1 : 0;
      const res = await fetch(`/telemetry?drop=${dropActive}`);
      const data = await res.json();
      
      const box = document.getElementById('stateBox');
      if (data.state === 0) {
        box.innerText = "IDLE / MANUAL OFF (0)";
        box.className = "status state-0";
      } else if (data.state === 1) {
        box.innerText = "LOCAL KNOB CONTROL (1)";
        box.className = "status state-1";
      } else if (data.state === 2) {
        box.innerText = "REMOTE WEB OVERRIDE (2)";
        box.className = "status state-2";
      } else if (data.state === 3) {
        box.innerText = "⚠️ WATCHDOG FAULT LOCKOUT - PRESS BREADBOARD BUTTON TO RESET (3)";
        box.className = "status state-3";
      }
      
      document.getElementById('speedVal').innerText = data.speed;
      document.getElementById('potVal').innerText = data.pot;

      if (!isDragging && (Date.now() - lastSliderMoveTime > 800)) {
        document.getElementById('slider').value = data.speed;
        document.getElementById('sliderLabel').innerText = data.speed;
      }
    }, 200);
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/telemetry")
def get_telemetry():
    # Only send <H> heartbeat if we are NOT simulating a Wi-Fi drop!
    if request.args.get("drop", "0") == "0":
        mqtt_client.publish("motor/cmd", "<H>")
    return jsonify(telemetry)

@app.route("/cmd", methods=["POST"])
def send_command():
    state = int(request.args.get("state", "0"))
    speed_arg = request.args.get("speed", None)

    if speed_arg is not None:
        speed = int(speed_arg)
        packet = f"<{state},{speed}>"
        telemetry["speed"] = speed
    else:
        packet = f"<{state}>"

    mqtt_client.publish("motor/cmd", packet)
    print(f"[Web -> MQTT] Published to motor/cmd: {packet}")
    return jsonify({"sent": packet})

if __name__ == "__main__":
    shown_host = socket.gethostname() + ".local" if DASHBOARD_HOST == "0.0.0.0" else DASHBOARD_HOST
    print(f"\n>>> OPEN 4-STATE MQTT DASHBOARD: http://{shown_host}:{DASHBOARD_PORT} <<<\n")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)