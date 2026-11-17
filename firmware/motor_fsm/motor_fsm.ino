// 4-state motor controller with a 2 s communication watchdog
// (pairs with src/serial_bridge.py + src/mqtt_dashboard.py)
//
// Protocol in : <1,speed> web override, <1> on, <0> off, <H> heartbeat
// Protocol out: <state,speed,pot> every 200 ms, state = 0..3

enum SystemState {
  STATE_MANUAL_OFF,     // 0: Motor OFF, ready
  STATE_MANUAL_ON,      // 1: Motor ON, physical knob control
  STATE_WEB_OVERRIDE,   // 2: Motor ON, web slider control (Watchdog ARMED)
  STATE_FAULT_LOCKOUT   // 3: EMERGENCY LOCK! Requires physical button press to clear
};

SystemState currentState = STATE_MANUAL_OFF;

const int BUTTON_PIN = 2;
const int POT_PIN    = A0;
const int MOTOR_PIN  = 9;

unsigned long lastTelemetryTime = 0;
unsigned long lastHeartbeatTime = 0;
unsigned long lastChange = 0;
const unsigned long DEBOUNCE_MS = 30;

bool lastReading = HIGH;
bool buttonState = HIGH;

char rxBuffer[16];
int rxIndex = 0;
bool isRecording = false;

int currentSpeed = 0;
int lockedPotBaseline = 0;

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
  // --- 1. INPUT: PHYSICAL BUTTON EDGE DETECTOR ---
  bool buttonJustPressed = false;
  bool reading = digitalRead(BUTTON_PIN);
  if (reading != lastReading) {
    lastChange = millis();
  }
  if ((millis() - lastChange) > DEBOUNCE_MS && reading != buttonState) {
    buttonState = reading;
    if (buttonState == LOW) {
      buttonJustPressed = true;
    }
  }
  lastReading = reading;

  // --- 2. INPUT: SMOOTHED POTENTIOMETER ---
  int potValue = readSmoothedPot();

  // --- 3. INPUT: SERIAL COMMANDS FROM PI (<state,speed> or <H>) ---
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '<') {
      rxIndex = 0;
      isRecording = true;
    } 
    else if (c == '>' && isRecording) {
      rxBuffer[rxIndex] = '\0';
      isRecording = false;
      lastHeartbeatTime = millis(); // Reset 2-second watchdog timer!

      // SAFETY GUARD: Ignore web ON/OFF commands if in STATE_FAULT_LOCKOUT!
      if (currentState != STATE_FAULT_LOCKOUT) {
        if (rxBuffer[0] == '1') {
          if (rxBuffer[1] == ',') {
            currentSpeed = constrain(atoi(&rxBuffer[2]), 0, 255);
          }
          lockedPotBaseline = potValue;
          currentState = STATE_WEB_OVERRIDE;
        } 
        else if (rxBuffer[0] == '0') {
          currentState = STATE_MANUAL_OFF;
        }
      }
    } 
    else if (isRecording && rxIndex < 15) {
      rxBuffer[rxIndex++] = c;
    }
  }

  // --- 4. BRAIN: 4-STATE FINITE STATE MACHINE ---
  switch (currentState) {

    case STATE_MANUAL_OFF:
      analogWrite(MOTOR_PIN, 0);
      if (buttonJustPressed) {
        currentState = STATE_MANUAL_ON;
      }
      break;

    case STATE_MANUAL_ON:
      if (abs(potValue - lockedPotBaseline) > 12) {
        currentSpeed = map(potValue, 0, 1023, 0, 255);
        lockedPotBaseline = potValue;
      }
      analogWrite(MOTOR_PIN, currentSpeed);
      if (buttonJustPressed) {
        currentState = STATE_MANUAL_OFF;
      }
      break;

    case STATE_WEB_OVERRIDE:
      analogWrite(MOTOR_PIN, currentSpeed);

      if (millis() - lastHeartbeatTime > 2000) {
        currentState = STATE_FAULT_LOCKOUT; // 2s Timeout -> Lockout!
      }
      else if (buttonJustPressed) {
        currentState = STATE_MANUAL_OFF;    // Button press -> Normal Off
      }
      else if (abs(potValue - lockedPotBaseline) > 75) {
        lockedPotBaseline = potValue;
        currentState = STATE_MANUAL_ON;     // Knob twist -> Manual On
      }
      break;

    case STATE_FAULT_LOCKOUT:
      analogWrite(MOTOR_PIN, 0);
      if (buttonJustPressed) {
        currentState = STATE_MANUAL_OFF;    // Physical reset clears the fault!
      }
      break;
  }

  // --- 5. OUTPUT: 200ms TELEMETRY (<0..3,speed,pot>) ---
  if (millis() - lastTelemetryTime >= 200) {
    lastTelemetryTime = millis();
    Serial.print("<");
    Serial.print((int)currentState); // Sends 0, 1, 2, or 3!
    Serial.print(",");
    Serial.print(currentSpeed);
    Serial.print(",");
    Serial.print(potValue);
    Serial.println(">");
  }
}