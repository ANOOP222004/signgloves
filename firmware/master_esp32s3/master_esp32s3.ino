// =============================================================
// Smart Glove — Master Firmware FINAL
// Board: ESP32-S3 DevKitC-1 (Right Hand)
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
//   The MPU6050 is mounted with its LONG EDGE facing toward the fingers.
//   This is a 90° rotation from the standard flat-on-wrist orientation.
//   Standard: Y axis along arm, X axis across wrist.
//   Your mount: X axis along arm (toward fingers), Y axis across wrist.
//   Fix applied: ax and ay are swapped in all orientation formulas.
//   Gyro axes are adjusted to match.
//
// YAW IMPLEMENTATION:
//   MPU6050 has no magnetometer so yaw cannot be derived from
//   accelerometer data alone (gravity has no yaw component).
//   Implementation: complementary filter.
//     - Gyro Z (after axis swap) is integrated for yaw angle.
//     - Yaw resets to 0 at startup. Drift is ~1-3 deg/min — acceptable
//       for 2-second gesture windows.
//     - The BiLSTM sees relative yaw change, not absolute heading.
//
// FILTER: Complementary filter for pitch and roll.
//   angle = 0.98 * (angle + gyro_rate * dt) + 0.02 * accel_angle
//   This blends gyro (fast, drifts slowly) with accelerometer
//   (slow/noisy, stable long-term). 0.98/0.02 split is standard.
//
// Packet format (19 fields, unchanged from Phase 1):
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
int frame_id = 0;
bool imu_ok  = false;
unsigned long last_time = 0;

// ── ESP-NOW receive callback ──────────────────────────────────
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
    imu_write(MPU6050_PWR_MGMT_1, 0x00);   // wake from sleep
    delay(100);
    imu_write(MPU6050_SMPLRT_DIV, 0x07);   // 125Hz sample rate
    imu_write(MPU6050_CONFIG, 0x03);        // DLPF 44Hz
    imu_write(MPU6050_GYRO_CONFIG, 0x00);   // +/-250 deg/s
    imu_write(MPU6050_ACCEL_CONFIG, 0x00);  // +/-2g

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
    // Read all 14 bytes in one I2C transaction
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(MPU6050_ACCEL_XOUT);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU6050_ADDR, 14, true);

    int16_t ax_raw = (Wire.read() << 8) | Wire.read();
    int16_t ay_raw = (Wire.read() << 8) | Wire.read();
    int16_t az_raw = (Wire.read() << 8) | Wire.read();
    Wire.read(); Wire.read();  // skip temperature
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
// Axis swap applied for 90-degree rotated mounting
// (long edge of IMU facing toward fingers)
void imu_update() {
    float axg, ayg, azg, gx_dps, gy_dps, gz_dps;
    imu_read_raw(&axg, &ayg, &azg, &gx_dps, &gy_dps, &gz_dps);

    // With long edge toward fingers:
    //   Physical pitch (wrist flex/extend) → sensor X axis → use ax, gx
    //   Physical roll  (wrist side-tilt)   → sensor Y axis → use ay, gy
    float pitch_accel = atan2f(axg, sqrtf(ayg*ayg + azg*azg)) * 180.0f / (float)PI;
    float roll_accel  = atan2f(-ayg, azg) * 180.0f / (float)PI;

    imu_pitch = COMP_GYRO * (imu_pitch + gx_dps * DT) + COMP_ACCEL * pitch_accel;
    imu_roll  = COMP_GYRO * (imu_roll  + gy_dps * DT) + COMP_ACCEL * roll_accel;
    imu_yaw  += gz_dps * DT;

    // Keep in range
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
    delay(2000);

    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    Serial.println("\n========================================");
    Serial.println("SMART GLOVE — MASTER ESP32-S3");
    Serial.println("========================================");
    Serial.printf("MAC ADDRESS: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    Serial.println("========================================\n");
    Serial.println("Starting in 5 seconds...");
    delay(5000);

    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    Wire.begin(IMU_SDA, IMU_SCL);
    Wire.setClock(400000);

    imu_ok = imu_init();
    if (imu_ok) {
        Serial.println("IMU: OK — complementary filter active");
        // Settle filter for 50 frames before sending
        for (int i = 0; i < 50; i++) {
            imu_update();
            delay((int)(DT * 1000));
        }
        imu_yaw = 0.0f;
        Serial.println("IMU: Settled. Yaw zeroed.");
    } else {
        Serial.println("ERR,1");
    }

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    if (esp_now_init() != ESP_OK) {
        Serial.println("ERROR: ESP-NOW init failed — halting");
        while (true) { delay(1000); }
    }

    esp_now_register_recv_cb(on_slave_data_received);

    slave_snapshot.thumb  = 2048;
    slave_snapshot.index  = 2048;
    slave_snapshot.middle = 2048;
    slave_snapshot.ring   = 2048;
    slave_snapshot.little = 2048;
    slave_snapshot.pitch  = 0.0f;
    slave_snapshot.roll   = 0.0f;
    slave_snapshot.yaw    = 0.0f;

    Serial.println("READY");
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
