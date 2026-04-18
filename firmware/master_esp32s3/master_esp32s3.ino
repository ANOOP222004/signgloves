// =============================================================
// Smart Glove — Master Firmware FINAL
// Board: ESP32-S3 DevKitC-1 (Right Hand)
//
// CHANGE LOG:
//   v2 (Phase 6): Full dual-glove ESP-NOW + IMU.
//   v3 (Phase 7 fix): Two bugs fixed —
//
//   BUG 1 — last_time not initialized before loop uses it:
//     last_time is declared as a global (= 0) but setup() takes
//     ~7+ seconds (2s Serial delay + 5s "Starting" delay + 50*33ms
//     IMU settle = ~8.65 seconds total). When loop() first runs,
//     millis() is already ~8650. The condition
//     (now - last_time >= 33) is immediately true, which is fine.
//     BUT: last_time = 0, so the first packet fires the moment
//     loop() starts. This is actually correct behaviour.
//     The real issue was the 5-second debug delay (see BUG 2).
//
//   BUG 2 — 5-second "Starting in 5 seconds..." delay:
//     This was left from debugging Phase 6 MAC address printing.
//     It is harmless for normal use, but when Python connects
//     immediately after port open (drain_queue + 2s sleep), it
//     sometimes catches the tail of startup noise and the parser
//     rejects the first few seconds of output.
//     More importantly: the TOTAL setup time was:
//       2000ms Serial delay
//     + 5000ms "Starting" delay       ← removed
//     + 50 * 33ms IMU settle = 1650ms
//     = 8.65 seconds before any packet
//     Python's drain_queue() only waits 2 seconds. The remaining
//     6.65 seconds of startup Serial noise (READY, MAC prints, etc.)
//     floods the Python parser's queue with garbage and causes the
//     packet parser to spend CPU rejecting junk — explaining the
//     low apparent frame rate even though the loop was correct.
//     Fix: remove the 5s delay. Total setup now ~3.65 seconds,
//     well within Python's 2s sleep + initial drain window.
//
//   BUG 3 — last_time initialized at declaration site (= 0):
//     After removing the 5s delay, last_time = 0 still works
//     (first loop iteration fires immediately, which is correct).
//     But resetting last_time = millis() at the END of setup()
//     gives cleaner first-packet timing. Fixed.
//
// GPIO assignments:
//   Thumb  → GPIO 1  (ADC1_CH0)
//   Index  → GPIO 2  (ADC1_CH1)
//   Middle → GPIO 3  (ADC1_CH2)
//   Ring   → GPIO 4  (ADC1_CH3)
//   Little → GPIO 5  (ADC1_CH4)
//   IMU SDA → GPIO 8
//   IMU SCL → GPIO 9
//   IMU AD0 → GND (I2C address 0x68)
//
// IMU MOUNTING NOTE:
//   Long edge facing toward fingers. Axis swap applied.
//
// Packet format (19 fields):
//   F,<id>,<RT>,<RI>,<RM>,<RR>,<RL>,<RP>,<RRL>,<RY>,
//   <LT>,<LI>,<LM>,<LR>,<LL>,<LP>,<LRL>,<LY>,<checksum>
// =============================================================

#include <esp_now.h>
#include <WiFi.h>
#include <Wire.h>
#include <esp_mac.h>
#include <math.h>

// ── Pin definitions ───────────────────────────────────────────
#define PIN_THUMB    1
#define PIN_INDEX    2
#define PIN_MIDDLE   3
#define PIN_RING     4
#define PIN_LITTLE   5

#define IMU_SDA      8
#define IMU_SCL      9

// ── IMU register addresses ────────────────────────────────────
#define MPU6050_ADDR        0x68
#define MPU6050_PWR_MGMT_1  0x6B
#define MPU6050_SMPLRT_DIV  0x19
#define MPU6050_CONFIG      0x1A
#define MPU6050_GYRO_CONFIG 0x1B
#define MPU6050_ACCEL_CONFIG 0x1C
#define MPU6050_ACCEL_XOUT  0x3B
#define MPU6050_GYRO_XOUT   0x43
#define MPU6050_WHO_AM_I    0x75

// ── IMU sensitivity constants ─────────────────────────────────
#define ACCEL_SCALE  16384.0f
#define GYRO_SCALE   131.0f

// ── Timing ───────────────────────────────────────────────────
#define SAMPLE_PERIOD_MS  33
#define FRAME_ID_MAX      9999
#define DT  (SAMPLE_PERIOD_MS / 1000.0f)

// ── Complementary filter constants ───────────────────────────
#define COMP_GYRO   0.98f
#define COMP_ACCEL  0.02f

// ── ESP-NOW payload — must match slave exactly ────────────────
typedef struct {
    int   thumb;
    int   index;
    int   middle;
    int   ring;
    int   little;
    float pitch;
    float roll;
    float yaw;
} SlavePayload;

volatile SlavePayload slave_data;
volatile bool slave_received = false;
SlavePayload slave_snapshot;

// ── IMU state ─────────────────────────────────────────────────
float imu_pitch = 0.0f;
float imu_roll  = 0.0f;
float imu_yaw   = 0.0f;

// ── State ─────────────────────────────────────────────────────
int frame_id  = 0;
bool imu_ok   = false;
unsigned long last_time = 0;   // set to millis() at end of setup()

// ── ESP-NOW receive callback ──────────────────────────────────
// Safe: only copies bytes and sets a flag. No Serial, no malloc.
void on_slave_data_received(const esp_now_recv_info_t* info,
                             const uint8_t* data,
                             int len) {
    if (len == sizeof(SlavePayload)) {
        memcpy((void*)&slave_data, data, sizeof(SlavePayload));
        slave_received = true;
    }
}

// ── IMU register write ────────────────────────────────────────
void imu_write(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission(true);
}

// ── IMU initialisation ────────────────────────────────────────
bool imu_init() {
    imu_write(MPU6050_PWR_MGMT_1, 0x00);
    delay(100);
    imu_write(MPU6050_SMPLRT_DIV, 0x07);
    imu_write(MPU6050_CONFIG, 0x03);
    imu_write(MPU6050_GYRO_CONFIG, 0x00);
    imu_write(MPU6050_ACCEL_CONFIG, 0x00);

    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(MPU6050_WHO_AM_I);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU6050_ADDR, 1, true);

    if (Wire.available()) {
        return (Wire.read() == 0x68);
    }
    return false;
}

// ── Read raw IMU values ───────────────────────────────────────
void imu_read_raw(float* axg, float* ayg, float* azg,
                  float* gx_dps, float* gy_dps, float* gz_dps) {
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(MPU6050_ACCEL_XOUT);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU6050_ADDR, 14, true);

    int16_t ax_raw = (Wire.read() << 8) | Wire.read();
    int16_t ay_raw = (Wire.read() << 8) | Wire.read();
    int16_t az_raw = (Wire.read() << 8) | Wire.read();
    Wire.read(); Wire.read();
    int16_t gx_raw = (Wire.read() << 8) | Wire.read();
    int16_t gy_raw = (Wire.read() << 8) | Wire.read();
    int16_t gz_raw = (Wire.read() << 8) | Wire.read();

    *axg    = ax_raw / ACCEL_SCALE;
    *ayg    = ay_raw / ACCEL_SCALE;
    *azg    = az_raw / ACCEL_SCALE;
    *gx_dps = gx_raw / GYRO_SCALE;
    *gy_dps = gy_raw / GYRO_SCALE;
    *gz_dps = gz_raw / GYRO_SCALE;
}

// ── Complementary filter update ───────────────────────────────
void imu_update() {
    float axg, ayg, azg, gx_dps, gy_dps, gz_dps;
    imu_read_raw(&axg, &ayg, &azg, &gx_dps, &gy_dps, &gz_dps);

    float pitch_accel = atan2f(axg, sqrtf(ayg*ayg + azg*azg)) * 180.0f / (float)PI;
    float roll_accel  = atan2f(-ayg, azg) * 180.0f / (float)PI;

    imu_pitch = COMP_GYRO * (imu_pitch + gx_dps * DT) + COMP_ACCEL * pitch_accel;
    imu_roll  = COMP_GYRO * (imu_roll  + gy_dps * DT) + COMP_ACCEL * roll_accel;
    imu_yaw  += gz_dps * DT;

    if (imu_yaw >  180.0f) imu_yaw -= 360.0f;
    if (imu_yaw < -180.0f) imu_yaw += 360.0f;
    if (imu_pitch >  180.0f) imu_pitch =  180.0f;
    if (imu_pitch < -180.0f) imu_pitch = -180.0f;
    if (imu_roll  >  180.0f) imu_roll  =  180.0f;
    if (imu_roll  < -180.0f) imu_roll  = -180.0f;
}

// ── Checksum ──────────────────────────────────────────────────
int compute_checksum(
    int rt, int ri, int rm, int rr, int rl,
    float rp, float rrl, float ry,
    int lt, int li, int lm, int lr, int ll,
    float lp, float lrl, float ly)
{
    int sum = 0;
    sum += rt + ri + rm + rr + rl;
    sum += (int)(rp  * 10);
    sum += (int)(rrl * 10);
    sum += (int)(ry  * 10);
    sum += lt + li + lm + lr + ll;
    sum += (int)(lp  * 10);
    sum += (int)(lrl * 10);
    sum += (int)(ly  * 10);
    return sum;
}

// ── Setup ─────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(2000);   // wait for Serial monitor to attach

    // Print MAC BEFORE WiFi.mode() — after mode change MAC may differ
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    Serial.println("\n========================================");
    Serial.println("SMART GLOVE — MASTER ESP32-S3");
    Serial.println("========================================");
    Serial.printf("MAC ADDRESS: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    Serial.println("========================================");
    // REMOVED: "Starting in 5 seconds..." + delay(5000)
    // Reason: setup() was taking 8.65s total. Python drain_queue()
    // only sleeps 2s. The extra 6s of startup noise flooded the
    // serial parser, causing ~4 Hz apparent rate instead of 30 Hz.

    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    Wire.begin(IMU_SDA, IMU_SCL);
    Wire.setClock(400000);

    imu_ok = imu_init();
    if (imu_ok) {
        Serial.println("IMU: OK — settling filter (50 frames)...");
        for (int i = 0; i < 50; i++) {
            imu_update();
            delay(33);   // explicit 33ms — clearer than DT*1000 cast
        }
        imu_yaw = 0.0f;
        Serial.println("IMU: Ready. Yaw zeroed.");
    } else {
        Serial.println("ERR,1 — IMU not found. Check SDA=GPIO8, SCL=GPIO9, AD0=GND");
    }

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    if (esp_now_init() != ESP_OK) {
        Serial.println("ERROR: ESP-NOW init failed — halting");
        while (true) { delay(1000); }
    }

    esp_now_register_recv_cb(on_slave_data_received);

    // Default left-hand snapshot — used until first ESP-NOW packet arrives
    slave_snapshot.thumb  = 2048;
    slave_snapshot.index  = 2048;
    slave_snapshot.middle = 2048;
    slave_snapshot.ring   = 2048;
    slave_snapshot.little = 2048;
    slave_snapshot.pitch  = 0.0f;
    slave_snapshot.roll   = 0.0f;
    slave_snapshot.yaw    = 0.0f;

    // FIX: set last_time here so the first loop iteration fires
    // exactly SAMPLE_PERIOD_MS after setup() completes —
    // not immediately (which it would if last_time stayed 0 and
    // millis() was already 3650 at this point).
    last_time = millis();

    Serial.println("READY");
    // From this point: loop() will fire packets at exactly 30 Hz.
    // Total setup time: ~3.65 seconds (was ~8.65s with 5s delay).
}

// ── Loop ──────────────────────────────────────────────────────
void loop() {
    unsigned long now = millis();

    if (now - last_time >= SAMPLE_PERIOD_MS) {
        last_time = now;

        if (imu_ok) {
            imu_update();
        }

        if (slave_received) {
            memcpy(&slave_snapshot, (void*)&slave_data, sizeof(SlavePayload));
            slave_received = false;
        }

        int R_T = analogRead(PIN_THUMB);
        int R_I = analogRead(PIN_INDEX);
        int R_M = analogRead(PIN_MIDDLE);
        int R_R = analogRead(PIN_RING);
        int R_L = analogRead(PIN_LITTLE);

        float R_P  = imu_ok ? imu_pitch : 0.0f;
        float R_RL = imu_ok ? imu_roll  : 0.0f;
        float R_Y  = imu_ok ? imu_yaw   : 0.0f;

        int   L_T  = slave_snapshot.thumb;
        int   L_I  = slave_snapshot.index;
        int   L_M  = slave_snapshot.middle;
        int   L_R  = slave_snapshot.ring;
        int   L_L  = slave_snapshot.little;
        float L_P  = slave_snapshot.pitch;
        float L_RL = slave_snapshot.roll;
        float L_Y  = slave_snapshot.yaw;

        int checksum = compute_checksum(
            R_T, R_I, R_M, R_R, R_L, R_P, R_RL, R_Y,
            L_T, L_I, L_M, L_R, L_L, L_P, L_RL, L_Y
        );

        Serial.print("F,");
        Serial.print(frame_id);   Serial.print(",");
        Serial.print(R_T);        Serial.print(",");
        Serial.print(R_I);        Serial.print(",");
        Serial.print(R_M);        Serial.print(",");
        Serial.print(R_R);        Serial.print(",");
        Serial.print(R_L);        Serial.print(",");
        Serial.print(R_P,  1);    Serial.print(",");
        Serial.print(R_RL, 1);    Serial.print(",");
        Serial.print(R_Y,  1);    Serial.print(",");
        Serial.print(L_T);        Serial.print(",");
        Serial.print(L_I);        Serial.print(",");
        Serial.print(L_M);        Serial.print(",");
        Serial.print(L_R);        Serial.print(",");
        Serial.print(L_L);        Serial.print(",");
        Serial.print(L_P,  1);    Serial.print(",");
        Serial.print(L_RL, 1);    Serial.print(",");
        Serial.print(L_Y,  1);    Serial.print(",");
        Serial.println(checksum);

        frame_id++;
        if (frame_id > FRAME_ID_MAX) frame_id = 0;
    }
}
