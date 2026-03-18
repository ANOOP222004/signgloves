// =============================================================
// Smart Glove - Phase 1: Full Packet Protocol Firmware
// Board  : ESP32 DevKit (Slave)
// Sensor : SS49E Hall Effect Sensor on GPIO 32 (Right Thumb)
//          All other fingers → dummy values (2048)
//          IMU → dummy values (0.0) — not yet connected
// Goal   : Stream full 19-field packet at 30 Hz
// =============================================================

// --- Pin Configuration ---
#define HALL_PIN_R_THUMB  32      // Only real sensor for now

// --- Sampling --- 
#define SAMPLE_PERIOD_MS  33      // 30 Hz

// --- Frame ID ---
#define FRAME_ID_MAX      9999
int frame_id = 0;

// --- Timing ---
unsigned long last_sample_time = 0;

// --- Dummy values for unconnected sensors ---
#define DUMMY_ADC   2048
#define DUMMY_IMU   0.0

// -------------------------------------------------------
// Checksum calculation
// Matches exactly what Python will verify on the other end
// checksum = sum of all int finger fields
//          + sum of int(each float IMU field * 10)
// -------------------------------------------------------
int compute_checksum(int rt, int ri, int rm, int rr, int rl,
                     float rp, float rrl, float ry,
                     int lt, int li, int lm, int lr, int ll,
                     float lp, float lrl, float ly) {
  int sum = 0;

  // Right fingers
  sum += rt; sum += ri; sum += rm; sum += rr; sum += rl;

  // Right IMU (multiply float by 10, cast to int)
  sum += (int)(rp  * 10);
  sum += (int)(rrl * 10);
  sum += (int)(ry  * 10);

  // Left fingers
  sum += lt; sum += li; sum += lm; sum += lr; sum += ll;

  // Left IMU
  sum += (int)(lp  * 10);
  sum += (int)(lrl * 10);
  sum += (int)(ly  * 10);

  return sum;
}

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  // Signal boot complete
  Serial.println("READY");
}

void loop() {
  unsigned long now = millis();

  if (now - last_sample_time >= SAMPLE_PERIOD_MS) {
    last_sample_time = now;

    // --- Read real sensor ---
    int R_T = analogRead(HALL_PIN_R_THUMB);

    // --- Dummy values for all other sensors ---
    int   R_I = DUMMY_ADC, R_M = DUMMY_ADC, R_R = DUMMY_ADC, R_L = DUMMY_ADC;
    float R_P = DUMMY_IMU, R_RL = DUMMY_IMU, R_Y = DUMMY_IMU;

    int   L_T = DUMMY_ADC, L_I = DUMMY_ADC, L_M = DUMMY_ADC;
    int   L_R = DUMMY_ADC, L_L = DUMMY_ADC;
    float L_P = DUMMY_IMU, L_RL = DUMMY_IMU, L_Y = DUMMY_IMU;

    // --- Compute checksum ---
    int checksum = compute_checksum(
      R_T, R_I, R_M, R_R, R_L, R_P, R_RL, R_Y,
      L_T, L_I, L_M, L_R, L_L, L_P, L_RL, L_Y
    );

    // --- Send packet ---
    // Format: F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,
    //         <R_P>,<R_RL>,<R_Y>,<L_T>,<L_I>,<L_M>,<L_R>,
    //         <L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>
    Serial.print("F,");
    Serial.print(frame_id);     Serial.print(",");

    // Right hand fingers
    Serial.print(R_T);          Serial.print(",");
    Serial.print(R_I);          Serial.print(",");
    Serial.print(R_M);          Serial.print(",");
    Serial.print(R_R);          Serial.print(",");
    Serial.print(R_L);          Serial.print(",");

    // Right hand IMU
    Serial.print(R_P,  1);      Serial.print(",");
    Serial.print(R_RL, 1);      Serial.print(",");
    Serial.print(R_Y,  1);      Serial.print(",");

    // Left hand fingers
    Serial.print(L_T);          Serial.print(",");
    Serial.print(L_I);          Serial.print(",");
    Serial.print(L_M);          Serial.print(",");
    Serial.print(L_R);          Serial.print(",");
    Serial.print(L_L);          Serial.print(",");

    // Left hand IMU
    Serial.print(L_P,  1);      Serial.print(",");
    Serial.print(L_RL, 1);      Serial.print(",");
    Serial.print(L_Y,  1);      Serial.print(",");

    // Checksum
    Serial.println(checksum);

    // --- Increment frame ID with rollover ---
    frame_id++;
    if (frame_id > FRAME_ID_MAX) {
      frame_id = 0;
    }
  }
}
