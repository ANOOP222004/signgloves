// =============================================================
// Smart Glove - Phase 1: Full Packet Protocol Firmware
// Board  : ESP32-S3 DevKit (Slave)
// Sensor : SS49E Hall Effect Sensor
// Goal   : Stream full 19-field packet at 30 Hz
// =============================================================

// --- Pin Configuration (ESP32-S3 ADC SAFE PINS) ---
#define HALL_PIN_R_THUMB   4
#define HALL_PIN_R_INDEX   5
#define HALL_PIN_R_MIDDLE  6
#define HALL_PIN_R_RING    7
#define HALL_PIN_R_LITTLE  8

// --- Sampling ---
#define SAMPLE_PERIOD_MS  33      // 30 Hz

// --- Frame ID ---
#define FRAME_ID_MAX      9999
int frame_id = 0;

// --- Timing ---
unsigned long last_sample_time = 0;

// --- Dummy values ---
#define DUMMY_ADC   2048
#define DUMMY_IMU   0.0

// -------------------------------------------------------
// Checksum calculation
// -------------------------------------------------------
int compute_checksum(int rt, int ri, int rm, int rr, int rl,
                     float rp, float rrl, float ry,
                     int lt, int li, int lm, int lr, int ll,
                     float lp, float lrl, float ly) {
  int sum = 0;

  sum += rt; sum += ri; sum += rm; sum += rr; sum += rl;

  sum += (int)(rp  * 10);
  sum += (int)(rrl * 10);
  sum += (int)(ry  * 10);

  sum += lt; sum += li; sum += lm; sum += lr; sum += ll;

  sum += (int)(lp  * 10);
  sum += (int)(lrl * 10);
  sum += (int)(ly  * 10);

  return sum;
}

void setup() {
  Serial.begin(115200);
  delay(1000);   // IMPORTANT for ESP32-S3 USB

  // ADC setup
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // Pin modes (stability)
  pinMode(HALL_PIN_R_THUMB, INPUT);
  pinMode(HALL_PIN_R_INDEX, INPUT);
  pinMode(HALL_PIN_R_MIDDLE, INPUT);
  pinMode(HALL_PIN_R_RING, INPUT);
  pinMode(HALL_PIN_R_LITTLE, INPUT);

  Serial.println("READY");
}

void loop() {
  unsigned long now = millis();

  if (now - last_sample_time >= SAMPLE_PERIOD_MS) {
    last_sample_time = now;

    // --- Read sensors ---
    int R_T = analogRead(HALL_PIN_R_THUMB);
    int R_I = analogRead(HALL_PIN_R_INDEX);
    int R_M = analogRead(HALL_PIN_R_MIDDLE);
    int R_R = analogRead(HALL_PIN_R_RING);
    int R_L = analogRead(HALL_PIN_R_LITTLE);

    // --- Dummy IMU ---
    float R_P = DUMMY_IMU, R_RL = DUMMY_IMU, R_Y = DUMMY_IMU;

    int   L_T = DUMMY_ADC, L_I = DUMMY_ADC, L_M = DUMMY_ADC;
    int   L_R = DUMMY_ADC, L_L = DUMMY_ADC;
    float L_P = DUMMY_IMU, L_RL = DUMMY_IMU, L_Y = DUMMY_IMU;

    // --- Checksum ---
    int checksum = compute_checksum(
      R_T, R_I, R_M, R_R, R_L, R_P, R_RL, R_Y,
      L_T, L_I, L_M, L_R, L_L, L_P, L_RL, L_Y
    );

    // --- Packet ---
    Serial.print("F,");
    Serial.print(frame_id); Serial.print(",");

    Serial.print(R_T); Serial.print(",");
    Serial.print(R_I); Serial.print(",");
    Serial.print(R_M); Serial.print(",");
    Serial.print(R_R); Serial.print(",");
    Serial.print(R_L); Serial.print(",");

    Serial.print(R_P, 1); Serial.print(",");
    Serial.print(R_RL, 1); Serial.print(",");
    Serial.print(R_Y, 1); Serial.print(",");

    Serial.print(L_T); Serial.print(",");
    Serial.print(L_I); Serial.print(",");
    Serial.print(L_M); Serial.print(",");
    Serial.print(L_R); Serial.print(",");
    Serial.print(L_L); Serial.print(",");

    Serial.print(L_P, 1); Serial.print(",");
    Serial.print(L_RL, 1); Serial.print(",");
    Serial.print(L_Y, 1); Serial.print(",");

    Serial.println(checksum);

    // --- Frame increment ---
    frame_id++;
    if (frame_id > FRAME_ID_MAX) {
      frame_id = 0;
    }
  }
}