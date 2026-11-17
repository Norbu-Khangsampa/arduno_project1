"""Pi GPIO check: the LED on GPIO 22 lights while the button on GPIO 17 is held."""

from gpiozero import LED, Button
from signal import pause

led = LED(22)  # same wiring as src/iot_node.py
button = Button(17)

def button_pressed():
    print("Sensor Triggered: LED ON")
    led.on()

def button_released():
    print("Sensor Cleared: LED OFF")
    led.off()

# Link the physical events to the Python functions
button.when_pressed = button_pressed
button.when_released = button_released

print("Hardware test running. Press the physical button... (Press Ctrl+C to exit)")

# Keep the script running to listen for events
pause()
