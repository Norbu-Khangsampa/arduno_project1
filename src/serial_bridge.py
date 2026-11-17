"""USB serial <-> MQTT bridge for the motor FSM.

Forwards commands from the "motor/cmd" topic to the Arduino and publishes the
Arduino's <state,speed,pot> telemetry to "motor/telemetry". Pairs with
firmware/motor_fsm and src/mqtt_dashboard.py.

Settings come from environment variables:
    SERIAL_PORT  (default /dev/ttyACM0)
    MQTT_BROKER  (default localhost)
    MQTT_PORT    (default 1883)
"""

import os
import threading
import time

import paho.mqtt.client as mqtt
import serial

SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyACM0")
BAUD_RATE = 9600
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))


def make_mqtt_client():
    """Create a client that works with both paho-mqtt 1.x and 2.x."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:  # paho-mqtt < 2.0
        return mqtt.Client()

ser = None
serial_lock = threading.Lock()  # Prevents MQTT thread and Main loop from colliding on USB!

def connect_arduino():
    """Safely opens (or re-opens) the USB connection if a motor current spike resets the port."""
    global ser
    while True:
        try:
            print(f"Connecting to {SERIAL_PORT}...")
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            new_ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.2)
            time.sleep(2.0)  # Wait for Arduino boot
            new_ser.reset_input_buffer()
            ser = new_ser
            print("Arduino USB Connected and Ready!")
            return
        except Exception as e:
            print(f"Waiting for {SERIAL_PORT} to come back online... ({e})")
            time.sleep(1.0)

# Initial connection
connect_arduino()

# Callback: Runs whenever a command arrives on "motor/cmd"
def on_message(client, userdata, msg):
    global ser
    command_str = msg.payload.decode('utf-8').strip()
    if command_str != "<H>":
        print(f"[MQTT -> Arduino] Forwarding command: {command_str}")
    
    with serial_lock:
        if ser is not None:
            try:
                ser.write((command_str + "\n").encode('utf-8'))
                ser.flush()
            except OSError:
                # Ignore write error here; the main loop will handle reconnecting
                pass

mqtt_client = make_mqtt_client()
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
mqtt_client.subscribe("motor/cmd")
mqtt_client.loop_start()

print("Fault-Tolerant Bridge Active! Streaming to 'motor/telemetry'...")

# Main Loop with Auto-Heal on OSError [Errno 5]
try:
    while True:
        try:
            line = None
            with serial_lock:
                if ser is not None and ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if line and line.startswith("<") and line.endswith(">"):
                mqtt_client.publish("motor/telemetry", line)

        except (OSError, serial.SerialException) as e:
            print(f"\n[WARNING] USB glitch detected ({e}). Auto-reconnecting...")
            with serial_lock:
                connect_arduino()

        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nStopping bridge...")
    mqtt_client.loop_stop()
    if ser is not None:
        ser.close()