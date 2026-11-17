"""Direct-serial motor dashboard: Flask web UI <-> Arduino over USB.

Pairs with firmware/motor_serial. Run on the Pi (or any computer with the
Arduino plugged in):

    python3 pi_motor_server.py                    # /dev/ttyACM0, all interfaces
    python3 pi_motor_server.py --port COM5        # Windows
    python3 pi_motor_server.py --host 127.0.0.1   # local access only
"""

import argparse
import atexit
import os
import socket
import threading
import time

import serial
from flask import Flask, jsonify, request, render_template_string

parser = argparse.ArgumentParser(description="Serial motor-control dashboard")
parser.add_argument("--port", default=os.environ.get("SERIAL_PORT", "/dev/ttyACM0"),
                    help="Arduino serial port (default: %(default)s)")
parser.add_argument("--baud", type=int, default=9600)
parser.add_argument("--host", default=os.environ.get("DASHBOARD_HOST", "0.0.0.0"),
                    help="interface to serve the dashboard on (default: %(default)s)")
parser.add_argument("--http-port", type=int, default=int(os.environ.get("DASHBOARD_PORT", "5000")))
args = parser.parse_args()

SERIAL_PORT = args.port
BAUD_RATE = args.baud

# Shared dictionary holding the latest telemetry from the Arduino
telemetry = {"state": 0, "speed": 0, "pot": 0, "connected": False}
write_lock = threading.Lock()   # serialises writes to the port (one reader + one writer is safe in pyserial)
stop_event = threading.Event()  # set once we start shutting down

print(f"Opening {SERIAL_PORT}...")
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.2)
ser.dtr = False
time.sleep(0.2)
ser.reset_input_buffer()
ser.dtr = True
print("Waiting 2.5s for Arduino reboot...")
time.sleep(2.5)
ser.reset_input_buffer()
telemetry["connected"] = True
print("Arduino Connected!")


def send(packet: bytes):
    """Thread-safe write to the Arduino."""
    with write_lock:
        ser.write(packet)
        ser.flush()


# --- BACKGROUND THREAD: continuously reads <state,speed,pot> from the Arduino ---
def serial_reader_thread():
    while not stop_event.is_set():
        try:
            raw = ser.readline()          # blocks up to the 0.2 s timeout
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if line.startswith("<") and line.endswith(">"):
                parts = line[1:-1].split(",")
                if len(parts) == 3:
                    telemetry["state"] = int(parts[0])
                    telemetry["speed"] = int(parts[1])
                    telemetry["pot"] = int(parts[2])
                    telemetry["connected"] = True
        except ValueError:
            pass                           # garbled line, ignore
        except (serial.SerialException, OSError):
            if stop_event.is_set():
                break
            telemetry["connected"] = False
            time.sleep(0.5)


threading.Thread(target=serial_reader_thread, daemon=True).start()


# --- CLEAN SHUTDOWN: runs on Ctrl+C and on normal exit ---
def shutdown_motor():
    if stop_event.is_set():
        return                             # already done
    stop_event.set()
    try:
        if ser.is_open:
            # <X> = "goodbye": Arduino stops the motor immediately and hands control
            # back to the physical button/knob. (Sent twice in case one byte is lost.)
            send(b"<X>\n<X>\n")
            time.sleep(0.1)
            ser.close()
        print("Motor stop sent, serial port closed.")
    except Exception as e:
        print(f"Shutdown warning: {e}")


atexit.register(shutdown_motor)

# --- FLASK WEB SERVER & DASHBOARD UI ---
app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <title>Mechatronics Layer 3 Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; background: #121212; color: #fff; text-align: center; padding: 30px; }
    .card { background: #1e1e1e; border-radius: 12px; padding: 25px; max-width: 480px; margin: auto; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .status { font-size: 24px; font-weight: bold; margin: 15px 0; padding: 10px; border-radius: 8px; }
    .on { background: #1b5e20; color: #a5d6a7; }
    .off { background: #b71c1c; color: #ef9a9a; }
    .metric { font-size: 18px; margin: 12px 0; background: #2c2c2c; padding: 12px; border-radius: 8px; }
    button { font-size: 18px; padding: 12px 24px; margin: 8px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
    .btn-on { background: #4caf50; color: white; }
    .btn-off { background: #f44336; color: white; }
    input[type=range] { width: 85%; margin: 15px 0; cursor: pointer; }
  </style>
</head>
<body>
  <div class="card">
    <h2>⚡ Layer 3: Motor Control Center</h2>
    <div id="stateBox" class="status off">MOTOR OFF (0)</div>
    <div class="metric">Active PWM Speed (0-255): <strong id="speedVal">0</strong></div>
    <div class="metric">Physical Knob ADC (0-1023): <strong id="potVal">0</strong></div>
    <hr style="border-color:#333; margin: 20px 0;">
    <h3>Remote Web Override</h3>
    <button class="btn-on" onclick="sendCmd(1, document.getElementById('slider').value)">TURN ON</button>
    <button class="btn-off" onclick="sendOff()">TURN OFF</button>
    <br><br>
    <label>Set Remote PWM Speed: <strong id="sliderLabel">180</strong></label><br>
    <input type="range" id="slider" min="0" max="255" value="180"
           onmousedown="isDragging = true"
           ontouchstart="isDragging = true"
           oninput="handleSliderDrag(this.value)"
           onchange="finishSliderDrag(this.value)">
  </div>

  <script>
    let isDragging = false;
    let lastSliderMoveTime = 0;

    function sendCmd(state, speed) {
      lastSliderMoveTime = Date.now();
      fetch(`/cmd?state=${state}&speed=${speed}`, { method: 'POST' }).catch(() => {});
    }

    function sendOff() {
      lastSliderMoveTime = Date.now();
      fetch(`/cmd?state=0`, { method: 'POST' }).catch(() => {});
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

    // --- HEARTBEAT: tells the Arduino "this page is still open" every 500 ms ---
    // When the tab closes these stop, and the Arduino shuts the motor off ~2 s later.
    // The ticks come from a Web Worker because browsers throttle normal timers
    // in background tabs (down to once a minute), which would trip the watchdog.
    function beat() {
      fetch('/heartbeat', { method: 'POST' }).catch(() => {});
    }
    beat();
    try {
      const worker = new Worker(URL.createObjectURL(
        new Blob(['setInterval(() => postMessage(0), 500);'], { type: 'text/javascript' })
      ));
      worker.onmessage = beat;
    } catch (e) {
      setInterval(beat, 500);   // fallback if Workers are unavailable
    }

    // --- TELEMETRY DISPLAY (read-only, no side effects on the Arduino) ---
    setInterval(async () => {
      try {
        const res = await fetch('/telemetry');
        const data = await res.json();

        const box = document.getElementById('stateBox');
        box.innerText = data.state === 1 ? "MOTOR ON (1)" : "MOTOR OFF (0)";
        box.className = data.state === 1 ? "status on" : "status off";

        document.getElementById('speedVal').innerText = data.speed;
        document.getElementById('potVal').innerText = data.pot;

        // Sync slider with Arduino's active speed once 800ms have passed after dragging
        if (!isDragging && (Date.now() - lastSliderMoveTime > 800)) {
          document.getElementById('slider').value = data.speed;
          document.getElementById('sliderLabel').innerText = data.speed;
        }
      } catch (e) {
        // server not reachable (e.g. Python was stopped): leave the display as-is
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
    return jsonify(telemetry)


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    # Forward the browser's "I'm still here" signal to the Arduino's watchdog.
    send(b"<H>\n")
    return ("", 204)


@app.route("/cmd", methods=["POST"])
def send_command():
    try:
        state = 1 if int(request.args.get("state", "0")) == 1 else 0
        speed_arg = request.args.get("speed", None)

        if speed_arg is not None:
            speed = max(0, min(255, int(speed_arg)))
            packet = f"<{state},{speed}>\n".encode("utf-8")
            telemetry["speed"] = speed
        else:
            packet = f"<{state}>\n".encode("utf-8")
    except ValueError:
        return jsonify({"error": "bad arguments"}), 400

    telemetry["state"] = state
    send(packet)
    print(f"Sent to Arduino: {packet.decode().strip()}")
    return jsonify({"sent": packet.decode().strip()})


if __name__ == "__main__":
    shown_host = socket.gethostname() + ".local" if args.host == "0.0.0.0" else args.host
    print(f"\n>>> OPEN THIS LINK IN YOUR BROWSER: http://{shown_host}:{args.http_port} <<<\n")
    try:
        app.run(host=args.host, port=args.http_port, debug=False)
    finally:
        shutdown_motor()