"""Serial smoke test: print everything the Arduino sends and send one test command.

    python3 serial_monitor.py                 # auto-detect the Arduino
    python3 serial_monitor.py --port COM5     # Windows
    python3 serial_monitor.py --port /dev/ttyACM0 --command "<1,180>"
"""

import argparse
import time

import serial
import serial.tools.list_ports


def guess_port():
    for port in serial.tools.list_ports.comports():
        text = f"{port.description} {port.manufacturer or ''}".lower()
        if any(k in text for k in ("arduino", "ch340", "usb serial", "acm")):
            return port.device
    return None


parser = argparse.ArgumentParser(description="Arduino serial smoke test")
parser.add_argument("--port", help="serial port (default: auto-detect)")
parser.add_argument("--baud", type=int, default=9600)
parser.add_argument("--command", default="<1,180>",
                    help="packet to send after 3 seconds (default: %(default)s)")
args = parser.parse_args()

print("Available serial ports:")
for port in serial.tools.list_ports.comports():
    print(f" -> {port.device} | {port.description}")

port = args.port or guess_port()
if port is None:
    raise SystemExit("No Arduino found. Pass the port explicitly with --port.")

print(f"\nOpening {port} at {args.baud} baud...")
ser = serial.Serial(port, args.baud, timeout=0.5)

# Toggle DTR so the Uno resets and boots cleanly
ser.dtr = False
time.sleep(0.2)
ser.reset_input_buffer()
ser.dtr = True

print("Waiting 2.5 seconds for the Arduino bootloader...")
time.sleep(2.5)
print("Connected. Printing raw messages from the Arduino (Ctrl+C to stop):\n")

start_time = time.time()
command_sent = False

try:
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line:
                print(f"RX: {line}")

        if not command_sent and time.time() - start_time > 3.0:
            print(f"\n>>> SENDING COMMAND: {args.command} <<<\n")
            ser.write(args.command.encode("utf-8") + b"\n")
            ser.flush()
            command_sent = True
        time.sleep(0.01)
except KeyboardInterrupt:
    print("\nTurning the motor off and closing the port...")
    ser.write(b"<0>\n")
    ser.flush()
    time.sleep(0.1)
    ser.close()
