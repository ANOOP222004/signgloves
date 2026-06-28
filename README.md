# 🖐️ AI Sign-to-Speech Smart Glove

> Real-time Indian Sign Language (ISL) recognition using sensor-embedded gloves, edge AI inference on ESP32-S3, and browser-based speech output — fully offline, no cloud required.

**Final Year B.Tech ECE Capstone Project**
M.S. Ramaiah University of Applied Sciences, Bengaluru — Batch 2022

🏆 **3rd Prize — ECE Department 8th Semester Project Exhibition, 5th June 2026**

---

## 📋 Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [System Architecture](#system-architecture)
- [Hardware](#hardware)
- [Circuit Diagrams](#circuit-diagrams)
- [Recognized Gestures](#recognized-gestures)
- [ML Model](#ml-model)
- [Smart Glove Dataset Studio](#smart-glove-dataset-studio)
- [Getting Started](#getting-started)
- [Repository Structure](#repository-structure)
- [Results](#results)
- [Team](#team)

---

## Overview

This project is a wearable two-glove system that recognizes **10 Indian Sign Language (ISL) gestures** in real time and converts them to spoken words. The complete AI inference pipeline runs on embedded hardware at the glove — no internet, no phone processing, no cloud.

Each glove has **5 Hall effect sensors** (SS49E) on the finger PIP joints and an **MPU6050 IMU** on the wrist. A **1D CNN model** (INT8 quantized, ~53 KB) runs directly on an ESP32-S3 and outputs the recognized sign as speech on any phone browser over WiFi.

**Key highlights:**
- 🧠 Edge AI — entire inference pipeline on a microcontroller (~53 KB model)
- 📡 Wireless — two gloves communicate via ESP-NOW at 30 Hz
- 🔊 Speech output — Web Speech API on phone browser over WiFi SoftAP
- 📊 98.1% test accuracy across 10 ISL gestures
- 🛠️ Purpose-built dataset collection desktop app (PyQt5)
- 🏆 3rd Prize at MSRUAS ECE Department Project Exhibition 2026

---

## How It Works

```
Wear gloves → perform ISL sign → hear spoken word  (~1 second end-to-end)
```

1. Power on both gloves
2. Connect phone to WiFi `SmartGlove_AP` (password: `smartglove123`)
3. Open browser → `192.168.4.1`
4. Perform any of the 10 ISL gestures
5. The recognized word is spoken aloud through your phone

---

## System Architecture

```
┌─────────────────────────┐         ┌──────────────────────────────────┐
│     LEFT GLOVE          │         │         RIGHT GLOVE              │
│     (Slave)             │         │         (Master)                 │
│                         │         │                                  │
│  5× SS49E Hall sensors  │ ESP-NOW │  5× SS49E Hall sensors           │
│  MPU6050 IMU            │────────►│  MPU6050 IMU                     │
│  ESP32 DevKit V1        │  30 Hz  │  ESP32-S3 N16R8                  │
│                         │         │         │                        │
└─────────────────────────┘         │  1D CNN Inference                │
                                    │  INT8 TFLite Micro (~53 KB)      │
                                    │         │                        │
                                    │  WiFi SoftAP → 192.168.4.1       │
                                    └─────────┼────────────────────────┘
                                              │
                                       Phone Browser
                                       Web Speech API
                                           🔊
```

**Data flow per prediction:**
1. Left glove reads 5 Hall sensors + IMU → sends 32-byte struct via ESP-NOW to right glove
2. Right glove reads its own 5 sensors + IMU → combines both hands → 16 raw features
3. Drop yaw from both IMUs (unreliable without magnetometer) → **14 features**
4. Collect 60 consecutive frames → shape `(60, 14)`
5. Per-channel z-score normalization → feed `(1, 60, 14)` tensor to 1D CNN
6. Confidence > 85% and same prediction 3 times in a row → speak gesture label

---

## Hardware

### Bill of Materials

| Component | Model | Qty | Purpose |
|---|---|---|---|
| Microcontroller (Master) | ESP32-S3 N16R8 DevKitC | 1 | ML inference + WiFi + ESP-NOW |
| Microcontroller (Slave) | ESP32 DevKit V1 TYPE-C 30-pin | 1 | Sensor reading + ESP-NOW send |
| Hall Effect Sensor | SS49E linear, TO-92 package | 10 | Finger bend detection (5 per hand) |
| IMU Module | MPU6050 GY-521 breakout | 2 | Wrist pitch and roll |
| Neodymium Magnet | N35, 5×5×2mm | 10 | Paired with each SS49E |
| LiPo Battery | KP 402535, 3.7V 500mAh | 2 | Power source per glove |
| Charger Module | TP4056 HW-373 with protection | 2 | LiPo charging and protection |
| Boost Converter | MT3608 2A step-up | 2 | 3.7V → 5V for ESP32 VIN |
| I2C Pull-up Resistor | 4.7kΩ, 1/4W | 4 | SDA and SCL pull-ups per IMU |
| Decoupling Capacitor | 10µF electrolytic | 2 | Power rail bulk decoupling |
| Bypass Capacitor | 100nF ceramic | 2 | High-frequency noise filtering |
| LED Resistor | 330Ω, 1/4W | 2 | Current limiting for power LED |
| Power Indicator | 3mm LED | 2 | Glove power-on indicator |
| Power Switch | Mini slide switch SPDT | 2 | Main power on/off |
| Wire | 30AWG silicone, multicolor | — | Flexible glove wiring |
| Glove | Lycra fabric, tight fit | 2 | Base glove |
| Sensor Mount | 3D printed PLA, 14×10×4mm | 10 | Finger-mounted sensor housing |
| Magnet Mount | 3D printed PLA, 8×8×3mm | 10 | Magnet holders on finger caps |
| Wrist Enclosure | 3D printed PLA, 78×48×18mm | 2 | Watch-style electronics case |

**Approximate total cost: ₹2,050 – ₹2,500 (both gloves)**

### GPIO Assignments

**Right Hand — Master (ESP32-S3 N16R8)**

| Finger | GPIO | Type |
|---|---|---|
| Thumb Hall sensor | GPIO 1 | ADC input |
| Index Hall sensor | GPIO 2 | ADC input |
| Middle Hall sensor | GPIO 3 | ADC input |
| Ring Hall sensor | GPIO 4 | ADC input |
| Little Hall sensor | GPIO 5 | ADC input |
| IMU SDA | GPIO 8 | I2C |
| IMU SCL | GPIO 9 | I2C |

**Left Hand — Slave (ESP32 DevKit V1)**

| Finger | GPIO | Type |
|---|---|---|
| Thumb Hall sensor | GPIO 32 | ADC input |
| Index Hall sensor | GPIO 33 | ADC input |
| Middle Hall sensor | GPIO 34 | ADC input-only |
| Ring Hall sensor | GPIO 35 | ADC input-only |
| Little Hall sensor | GPIO 36 (VP) | ADC input-only |
| IMU SDA | GPIO 21 | I2C |
| IMU SCL | GPIO 22 | I2C |

> ⚠️ **Critical:** GPIO 25 on the DevKit V1 is a DAC output — it drives 0V at boot and cannot be used as a sensor input. GPIO 36 (VP) is the correct input-only alternative for the little finger.

### Power Chain

```
LiPo 3.7V  →  TP4056 (BAT+/BAT−)  →  MT3608 (boost to 5V)  →  Slide Switch  →  ESP32 VIN
                                                                                      │
                                                                               ESP32 3V3 out
                                                                                      │
                                                             ┌────────────────────────┤
                                                             │                        │
                                                     5× SS49E sensors          MPU6050 IMU
                                                     (VCC → 3.3V)           (VCC → 3.3V)
```

---

## Circuit Diagrams

### Left Glove — Slave Circuit (ESP32 DevKit V1)

![Left Glove Circuit](hardware/left_glove_circuit.png)

### Right Glove — Master Circuit (ESP32-S3 N16R8)

![Right Glove Circuit](hardware/right_glove_circuit.png)

> Full component list with quantities and prices: [`hardware/BOM.md`](hardware/BOM.md)

---

## Recognized Gestures

The system recognizes these 10 ISL signs:

| # | Gesture | Speech Output |
|---|---|---|
| 1 | HELLO | "hello" |
| 2 | STUDY | "study" |
| 3 | YES | "yes" |
| 4 | NO | "no" |
| 5 | THANKYOU | "thank you" |
| 6 | SORRY | "sorry" |
| 7 | HELP | "help" |
| 8 | WATER | "water" |
| 9 | PLEASE | "please" |
| 10 | FRIENDS | "friends" |

> ⚠️ Label order is frozen after the first data export. The model learns by index position. Reordering silently corrupts all predictions. New gestures can only be appended to the end.

---

## ML Model

### Architecture — 1D CNN

```
Input: (1, 60, 14)   ← 60 frames × 14 features
    ↓
Conv1D(32, kernel=3, ReLU) → MaxPooling1D(2) → Dropout(0.3)
    ↓
Conv1D(64, kernel=3, ReLU) → MaxPooling1D(2) → Dropout(0.3)
    ↓
Conv1D(64, kernel=3, ReLU) → GlobalAveragePooling1D()
    ↓
Dense(64, ReLU) → Dropout(0.4)
    ↓
Dense(10, Softmax)   ← 10 ISL gesture classes
```

### Specifications

| Property | Value |
|---|---|
| Input shape | (1, 60, 14) |
| Total parameters | 23,242 |
| Float32 size | ~97 KB |
| INT8 quantized size | **~53 KB** |
| Validation accuracy | **97.48%** |
| Test accuracy | **98.1%** |
| Inference hardware | ESP32-S3 N16R8 via TFLite Micro |
| Training environment | Google Colab T4 GPU |
| Framework | TensorFlow/Keras → TFLite → TFLite Micro INT8 |

### Feature Engineering

```
Raw: 16 channels (5 Hall + pitch/roll/yaw per hand × 2 hands)
  → Drop yaw from both IMUs (channels 7 and 15) — drifts without magnetometer
  → 14 features per frame
  → Collect 60 frames (2 seconds at 30 Hz) → shape (60, 14)
  → Per-channel z-score normalization (per sample, not stored stats)
  → Reshape to (1, 60, 14) → model input
```

**Why yaw is excluded:** Gyroscope integration without a magnetometer causes drift and wraparound at ±180°. Pitch and roll from the complementary filter are stable and discriminative enough for the 10 gestures.

**Why z-score per sample:** Normalizing per channel per sample (rather than from stored training statistics) makes the model immune to calibration drift between sessions and between different users.

### Training

| Setting | Value |
|---|---|
| Dataset | 1,851 labeled samples across 10 gestures |
| Split | Stratified 80/10/10 (seed=42) |
| Confidence threshold | 0.85 |
| Stability filter | 3 consecutive identical predictions |
| Output cooldown | 2 seconds between spoken outputs |
| Primary confusion pair | SORRY ↔ PLEASE |

### Why 1D CNN over BiLSTM

BiLSTM was tested and produced identical wrong predictions on the same confusion pairs — errors were data-driven, not architecture-driven. 1D CNN was chosen for its significant size advantage: ~53 KB vs ~499 KB, and faster inference on ESP32-S3.

---

## Smart Glove Dataset Studio

A purpose-built **PyQt5 desktop application** for recording, managing, analyzing, and exporting the ISL gesture dataset. Built across 10 phases alongside the hardware.

### Features

- Live 30 Hz sensor signal visualization with scrolling per-channel graphs
- Real-time 3D hand skeleton mirroring physical glove movement
- Gesture recording with offline voice command control ("start", "save", "discard")
- Multi-user calibration profiles with open-hand and closed-hand wizard
- Dataset analysis: per-gesture sample counts, outlier detection, class balance view
- Stratified 80/10/10 ML export → NumPy arrays ready for Colab training
- USB Serial and WiFi UDP connection modes

### Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| UI | PyQt5 |
| Signal plots | PyQtGraph |
| 3D skeleton | PyQtGraph OpenGL |
| Serial comms | pyserial |
| Voice control | Vosk (offline, vosk-model-small-en-us-0.15) |
| ML export | NumPy |
| OS | Ubuntu 22.04 |

---

## Getting Started

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Ubuntu | 22.04 | WSL2 on Windows also works |
| Python | 3.10+ | |
| Arduino IDE | 2.x | |
| ESP32 Arduino Core | **2.0.17 exactly** | Core 3.x causes cc1plus segfault with TFLite |

### 1. Clone the Repository

```bash
git clone https://github.com/ANOOP222004/signgloves.git
cd signgloves
```

### 2. Flash Slave Firmware (Left Hand — ESP32 DevKit V1)

Open `firmware/slave_esp32/slave_esp32.ino` in Arduino IDE.

```
Board: ESP32 Dev Module
Port:  /dev/ttyUSB0
Upload Speed: 921600
```

### 3. Flash Master Firmware (Right Hand — ESP32-S3 N16R8)

Open `firmware/master_esp32s3/master_esp32s3.ino` in Arduino IDE.

```
Board: ESP32S3 Dev Module
USB CDC On Boot: Enabled
Flash Size: 16MB (128Mb)
PSRAM: OPI PSRAM
Port: /dev/ttyACM0  ← right USB-C port = UART port
```

### 4. Set Up Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
cd smart_dataset_studio
pip install -r requirements.txt
```

### 5. Download Vosk Voice Model

```bash
cd smart_dataset_studio/voice/
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

### 6. Run Dataset Studio

```bash
cd smart_dataset_studio
python3 main.py
```

On startup: select USB Serial → create calibration profile → complete open/close hand wizard → record gestures on the Record tab.

### 7. Train the Model (Google Colab)

1. Export dataset from Dataset Studio (Export tab → `.npy` files)
2. Upload to Google Drive
3. Open `ml/SmartGlove_Phase9_CNN_v3_fingers_only.ipynb` in Colab (T4 GPU)
4. Run all cells → download `model_v6.tflite` (~53 KB)

### 8. Live Inference

**Phone browser (wireless speech output):**
1. Power on both gloves
2. Phone WiFi → `SmartGlove_AP` — password: `smartglove123`
3. Browser → `http://192.168.4.1`
4. Perform gestures — recognized words spoken aloud

**PC terminal:**
```bash
source venv/bin/activate
python3 live_inference.py
```

---

## Repository Structure

```
signgloves/
│
├── README.md
├── .gitignore
│
├── firmware/
│   ├── master_esp32s3/
│   │   └── master_esp32s3.ino    ← TFLite inference, WiFi SoftAP, ESP-NOW receive
│   └── slave_esp32/
│       └── slave_esp32.ino       ← Sensor reading, ESP-NOW transmit
│
├── smart_dataset_studio/         ← PyQt5 dataset collection app
│   ├── main.py
│   ├── config.py                 ← all constants, no magic numbers elsewhere
│   ├── requirements.txt
│   ├── ui/                       ← PyQt5 tabs and panels
│   ├── communication/            ← serial thread, packet parser
│   ├── processing/               ← EMA filter, calibration, frame builder
│   ├── recording/                ← 60-frame gesture state machine
│   ├── dataset/                  ← dataset manager, ML export worker
│   ├── visualization/            ← signal plots, 3D hand skeleton
│   └── voice/                    ← Vosk offline voice listener
│
├── ml/
│   ├── SmartGlove_Phase9_CNN_v3_fingers_only.ipynb  ← Colab training notebook
│   ├── model_v6.tflite           ← INT8 quantized model (~53 KB)
│   └── results/
│       ├── confusion_matrix.png
│       └── training_curves.png
│
├── hardware/
│   ├── BOM.md                    ← Bill of Materials with costs
│   ├── left_glove_circuit.png    ← Left hand slave wiring diagram
│   └── right_glove_circuit.png   ← Right hand master wiring diagram
│
├── docs/
│   └── phase_docs/               ← Phase-by-phase build documentation
│
└── media/
    └── glove_photo.jpg           ← Photo of assembled gloves
```

---

## Results

| Metric | Value |
|---|---|
| Test Accuracy | **98.1%** |
| Validation Accuracy | **97.48%** |
| Model Size (INT8) | **~53 KB** |
| Parameters | **23,242** |
| Dataset | 1,851 labeled samples |
| Gestures | 10 ISL signs |
| End-to-End Latency | ~1 second |
| Inference Hardware | ESP32-S3 N16R8 |
| Primary Confusion Pair | SORRY ↔ PLEASE |
| Exhibition | 🏆 3rd Prize — MSRUAS ECE Dept. Exhibition, 5 June 2026 |

---

## Team

| Name | Role |
|---|---|
| Anoop B A | Hardware design, firmware, ML model, dataset studio |
| Nawaz Khan | Hardware assembly, testing |
| Harikrishna K R | Hardware assembly, testing |

**Supervisors:** Mrs. Deepthi S (Guide) · Dr. B R Karthikeyan (Co-Guide)

**Institution:** M.S. Ramaiah University of Applied Sciences, RTC Peenya, Bengaluru
**Department:** Electronics and Communication Engineering · Batch 2022

---

*Built to demonstrate real-time edge AI for assistive communication technology.*
