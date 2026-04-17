// =============================================================
// Smart Glove — Slave Firmware FINAL WITH IMU
// Board: ESP32 DevKit V1 (Left Hand)
//
// WHAT CHANGED FROM PREVIOUS VERSION:
//   Previous version had no IMU code at all — pitch/roll/yaw
//   were hardcoded to 0.0. Now has full MPU6050 support with
//   the same complementary filter as master.
//
// GPIO assignments (Hall sensors):
//   Thumb  → GPIO 32
//   Index  → GPIO 33
//   Middle → GPIO 34
//   Ring   → GPIO 35
//   Little → GPIO 36 (VP) instood of 25
//
// GPIO assignments (IMU):
//   SDA → GPIO 21  (standard ESP32 DevKit V1 I2C SDA pin)
//   SCL → GPIO 22  (standard ESP32 DevKit V1 I2C SCL pin)
//   AD0 → GND      (I2C address 0x68)
//   4.7k pull-up resistors on SDA and SCL to 3V3
//
// IMU MOUNTING:
//   Same mounting as master — long edge facing toward fingers.
//   Same axis swap applied (ax and ay swapped in formulas).
//   Same gx/gy swap for gyro rates.
//
// MASTER MAC: update MASTER_MAC if you replaced the master chip.
// =============================================================

#include <esp_now.h>
#include <WiFi.h>
#include <Wire.h>
#include <esp_mac.h>
#include <math.h>

// ── Hall sensor pins ──────────────────────────────────────────
#define PIN_THUMB   32
#define PIN_INDEX   33
#define PIN_MIDDLE  34
#define PIN_RING    35
#define PIN_LITTLE  36

// ── IMU I2C pins ──────────────────────────────────────────────
// GPIO 21 and 22 are the standard hardware I2C pins on ESP32 DevKit V1.
// Do NOT use GPIO 8/9 — those are the ESP32-S3 master pins.
#define IMU_SDA     21
#define IMU_SCL     22

// ── IMU register addresses ────────────────────────────────────
#define MPU6050_ADDR         0x68
#define MPU6050_PWR_MGMT_1   0x6B
#define MPU6050_SMPLRT_DIV   0x19
#define MPU6050_CONFIG       0x1A
#define MPU6050_GYRO_CONFIG  0x1B
#define MPU6050_ACCEL_CONFIG 0x1C
#define MPU6050_ACCEL_XOUT   0x3B
#define MPU6050_WHO_AM_I     0x75

// ── IMU sensitivity ───────────────────────────────────────────
#define ACCEL_SCALE  16384.0f   // +/-2g  = 16384 LSB/g
#define GYRO_SCALE   131.0f     // +/-250 deg/s = 131 LSB/(deg/s)

// ── Timing ───────────────────────────────────────────────────
#define SAMPLE_PERIOD_MS  33    // 30 Hz
#define DT  (SAMPLE_PERIOD_MS / 1000.0f)  // 0.033 seconds

// ── Complementary filter ──────────────────────────────────────
#define COMP_GYRO   0.98f
#define COMP_ACCEL  0.02f

// ── Master MAC address ────────────────────────────────────────
// Update this if master chip was ever replaced.
// Get correct MAC by opening Serial Monitor on master at startup.
uint8_t MASTER_MAC[6] = {0x3C, 0x0F, 0x02, 0xD6, 0x46, 0xE8};

// ── ESP-NOW payload — must match master struct exactly ────────
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

SlavePayload payload;

// ── IMU state ─────────────────────────────────────────────────
float imu_pitch = 0.0f;
float imu_roll  = 0.0f;
float imu_yaw   = 0.0f;
bool  imu_ok    = false;

// ── ESP-NOW send callback ─────────────────────────────────────
// Cast required for newer ESP32 Arduino core versions.
void on_data_sent(const uint8_t* mac_addr, esp_now_send_status_t status) {
    if (status != ESP_NOW_SEND_SUCCESS) {
        Serial.println("WARNING: ESP-NOW send failed");
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
    imu_write(MPU6050_SMPLRT_DIV, 0x07);   // 125 Hz internal sample rate
    imu_write(MPU6050_CONFIG, 0x03);        // DLPF bandwidth 44 Hz
    imu_write(MPU6050_GYRO_CONFIG, 0x00);   // +/-250 deg/s full scale
    imu_write(MPU6050_ACCEL_CONFIG, 0x00);  // +/-2g full scale

    // Verify WHO_AM_I — MPU6050 returns 0x68
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
    // Read all 14 bytes in one transaction: accel(6) + temp(2) + gyro(6)
    Wire.beginTransmission(MPU6050_ADDR);
    Wire.write(MPU6050_ACCEL_XOUT);
    Wire.endTransmission(false);
    Wire.requestFrom(MPU6050_ADDR, 14, true);

    int16_t ax_raw = (Wire.read() << 8) | Wire.read();
    int16_t ay_raw = (Wire.read() << 8) | Wire.read();
    int16_t az_raw = (Wire.read() << 8) | Wire.read();
    Wire.read(); Wire.read();  // skip temperature bytes
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
// Axis swap for 90-degree rotated mounting (long edge toward fingers).
// Identical logic to master — same physical mounting on both hands.
void imu_update() {
    float axg, ayg, azg, gx_dps, gy_dps, gz_dps;
    imu_read_raw(&axg, &ayg, &azg, &gx_dps, &gy_dps, &gz_dps);

    // Axis swap: long edge toward fingers means physical pitch
    // is captured on sensor X axis, physical roll on sensor Y axis.
    float pitch_accel = atan2f(axg, sqrtf(ayg*ayg + azg*azg)) * 180.0f / (float)PI;
    float roll_accel  = atan2f(-ayg, azg) * 180.0f / (float)PI;

    // Complementary filter — 98% gyro, 2% accel
    imu_pitch = COMP_GYRO * (imu_pitch + gx_dps * DT) + COMP_ACCEL * pitch_accel;
    imu_roll  = COMP_GYRO * (imu_roll  + gy_dps * DT) + COMP_ACCEL * roll_accel;

    // Yaw from gyro Z integration (Z axis unchanged by horizontal rotation)
    imu_yaw += gz_dps * DT;

    // Keep yaw in -180 to +180 range
    if (imu_yaw >  180.0f) imu_yaw -= 360.0f;
    if (imu_yaw < -180.0f) imu_yaw += 360.0f;

    // Clamp pitch and roll
    if (imu_pitch >  180.0f) imu_pitch =  180.0f;
    if (imu_pitch < -180.0f) imu_pitch = -180.0f;
    if (imu_roll  >  180.0f) imu_roll  =  180.0f;
    if (imu_roll  < -180.0f) imu_roll  = -180.0f;
}

// ── Setup ─────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("========================================");
    Serial.println("SMART GLOVE — SLAVE ESP32 WITH IMU");
    Serial.println("========================================");

    // Print slave MAC
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    Serial.printf("SLAVE MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    // ADC
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);

    // I2C for IMU — using GPIO 21 (SDA) and 22 (SCL)
    // These are the standard hardware I2C pins on ESP32 DevKit V1
    Wire.begin(IMU_SDA, IMU_SCL);
    Wire.setClock(400000);  // 400 kHz fast mode

    // IMU init
    imu_ok = imu_init();
    if (imu_ok) {
        Serial.println("IMU: OK — complementary filter active");
        // Settle filter for 50 frames before starting
        for (int i = 0; i < 50; i++) {
            imu_update();
            delay((int)(DT * 1000));
        }
        imu_yaw = 0.0f;
        Serial.println("IMU: Settled. Yaw zeroed.");
    } else {
        Serial.println("IMU: FAIL — check SDA=GPIO21, SCL=GPIO22, AD0=GND");
        Serial.println("IMU: Sending 0.0 for pitch/roll/yaw");
    }

    // WiFi station mode for ESP-NOW
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    // Guard: halt if MASTER_MAC is all zeros
    bool mac_is_zero = true;
    for (int i = 0; i < 6; i++) {
        if (MASTER_MAC[i] != 0x00) { mac_is_zero = false; break; }
    }
    if (mac_is_zero) {
        Serial.println("ERROR: MASTER_MAC is all zeros — update and reflash");
        while (true) { delay(1000); }
    }

    // ESP-NOW init
    if (esp_now_init() != ESP_OK) {
        Serial.println("ERROR: ESP-NOW init failed — halting");
        while (true) { delay(1000); }
    }

    // Register callback with cast for newer Arduino core compatibility
    esp_now_register_send_cb((esp_now_send_cb_t)on_data_sent);

    // Register master as peer
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, MASTER_MAC, 6);
    peer.channel = 0;
    peer.encrypt = false;

    if (esp_now_add_peer(&peer) != ESP_OK) {
        Serial.println("ERROR: Failed to add master as peer — halting");
        while (true) { delay(1000); }
    }

    Serial.println("Slave ready — transmitting at 30 Hz");
    Serial.println("========================================");
}

// ── Loop ──────────────────────────────────────────────────────
unsigned long last_time = 0;

void loop() {
    unsigned long now = millis();

    if (now - last_time >= SAMPLE_PERIOD_MS) {
        last_time = now;

        // Update IMU filter every frame for accurate gyro integration
        if (imu_ok) {
            imu_update();
        }

        // Read Hall sensors
        payload.thumb  = analogRead(PIN_THUMB);
        payload.index  = analogRead(PIN_INDEX);
        payload.middle = analogRead(PIN_MIDDLE);
        payload.ring   = analogRead(PIN_RING);
        payload.little = analogRead(PIN_LITTLE);

        // IMU values from complementary filter
        // If IMU failed, sends 0.0 (safe fallback)
        payload.pitch = imu_ok ? imu_pitch : 0.0f;
        payload.roll  = imu_ok ? imu_roll  : 0.0f;
        payload.yaw   = imu_ok ? imu_yaw   : 0.0f;

        // Send to master via ESP-NOW
        esp_now_send(MASTER_MAC, (uint8_t*)&payload, sizeof(payload));
    }
}
