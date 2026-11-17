// Direct-serial motor controller (pairs with src/pi_motor_server.py)
//
// Protocol in : <1,speed> on, <1> on, <0> off, <H> heartbeat, <X> stop + release
// Protocol out: <motorOn,speed,pot> every 200 ms

unsigned long lastHeartbeatTime = 0;
unsigned long lastTelemetryTime = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 200; // Report 5 times per second

const int BUTTON_PIN = 2;
const int POT_PIN    = A0;
const int MOTOR_PIN  = 9;   // PWM pin

bool motorOn = false;
bool lastReading = HIGH;
bool buttonState = HIGH;
unsigned long lastChange = 0;
const unsigned long DEBOUNCE_MS = 30;

char rxBuffer[16];          // Scratchpad array to hold incoming characters
int rxIndex = 0;            // Current slot in the array
bool isRecording = false;   // Are we currently inside '<' and '>'?

int currentSpeed = 0;       // Stores the active PWM speed (0-255)
int lockedPotBaseline = 0;  // Averaged knob baseline when Web takes control
bool webOverride = false;   // true = Web Slider controls speed; false = Physical Knob controls speed

// Helper function: averages 8 quick ADC readings to cancel out DC motor brush noise!
int readSmoothedPot() {
  long sum = 0;
  for (int i = 0; i < 8; i++) {
    sum += analogRead(POT_PIN);
  }
  return (int)(sum / 8);
}

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(MOTOR_PIN, OUTPUT);
  analogWrite(MOTOR_PIN, 0);
  Serial.begin(9600);

  lockedPotBaseline = readSmoothedPot();
  currentSpeed = map(lockedPotBaseline, 0, 1023, 0, 255);
}

void loop() {
  // --- 1. PHYSICAL BUTTON CHECK (Non-Blocking Debounce) ---
  bool reading = digitalRead(BUTTON_PIN);
  if (reading != lastReading) {
    lastChange = millis();
  }

  if ((millis() - lastChange) > DEBOUNCE_MS && reading != buttonState) {
    buttonState = reading;
    if (buttonState == LOW) {
      motorOn = !motorOn;   // Toggle on each press
      webOverride = false;  // a physical press always takes control back from the web
    }
  }
  lastReading = reading;

  // --- 2. NON-BLOCKING SERIAL FRAMING (<state,speed>) ---
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '<') {
      rxIndex = 0;
      isRecording = true;
    } 
    else if (c == '>' && isRecording) {
      rxBuffer[rxIndex] = '\0';
      isRecording = false;
      lastHeartbeatTime = millis();

      if (rxBuffer[0] == '1') {
        motorOn = true;
        webOverride = true; // arm the watchdog whenever the Web turns the motor ON
      } else if (rxBuffer[0] == '0') {
        motorOn = false;
      } else if (rxBuffer[0] == 'X') {
        // server is shutting down: stop now and hand control back to the button/knob
        motorOn = false;
        webOverride = false;
      }

      // If command includes a speed (e.g. <1,120>), lock into WEB OVERRIDE mode!
      if (rxBuffer[1] == ',') {
        currentSpeed = atoi(&rxBuffer[2]); 
        currentSpeed = constrain(currentSpeed, 0, 255);
        webOverride = true; // Web slider is now locked in charge!

        // Apply new motor speed first, then record the smoothed knob baseline
        if (motorOn) {
          analogWrite(MOTOR_PIN, currentSpeed);
        }
        lockedPotBaseline = readSmoothedPot();
      }
    }
    else if (isRecording) {
      if (rxIndex < 15) {
        rxBuffer[rxIndex] = c;
        rxIndex++;
      }
    }
  }

  // --- 3. POTENTIOMETER CHECK (Smoothed + Web Lockout Protection) ---
  int potValue = readSmoothedPot();

  if (webOverride) {
    // While locked to Web Slider, ignore motor noise! Only unlock if user turns knob by > 75 counts
    if (abs(potValue - lockedPotBaseline) > 75) {
      webOverride = false; // Hand control back to the physical knob!
      lockedPotBaseline = potValue;
    }
  }

  // If physical knob is in charge, track it smoothly (deadband of 12 to stop 1-count flicker)
  if (!webOverride) {
    if (abs(potValue - lockedPotBaseline) > 12) {
      currentSpeed = map(potValue, 0, 1023, 0, 255);
      lockedPotBaseline = potValue;
    }
  }

  // --- 4. DRIVE MOTOR OUTPUT ---
  if (motorOn) {
    analogWrite(MOTOR_PIN, currentSpeed);
  } else {
    analogWrite(MOTOR_PIN, 0);
  }

  // --- 5. NON-BLOCKING TELEMETRY HEARTBEAT (Every 200 ms) ---
  if (millis() - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = millis();

    Serial.print("<");
    Serial.print(motorOn);
    Serial.print(",");
    Serial.print(currentSpeed);
    Serial.print(",");
    Serial.print(potValue);
    Serial.println(">");
  }
  // --- LAYER 4: COMMUNICATION WATCHDOG (2-Second Dead Man's Switch) ---
  // If Web Override is active and no <H> heartbeat arrives for 2000 ms, shut motor OFF!
  if (webOverride && motorOn && (millis() - lastHeartbeatTime > 2000)) {
    motorOn = false;
    webOverride = false;
  }
}