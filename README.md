# FBI Remote Install Enhanced (v3)

A **colorful, tolerant, quality-of-life–focused** enhancement of the classic `servefiles.py` workflow for **FBI Remote Install** on Nintendo 3DS.

This project is designed to make **network CIA installs less painful**, more informative, and more resilient to FBI’s flaky ACK behavior.

---

## ✨ Features

### 🚀 Core Improvements
- **Default 3DS IP**: `192.168.1.76` (press Enter to accept)
- **Drag & drop** a single CIA *or* an entire folder
- **Batch installs** (multiple CIAs sent at once)
- **Fire-and-forget URL sending**
  - Missing ACKs no longer kill the run
- **Hotkey controls while running**
  - `R + Enter` → re-send URLs
  - `Q + Enter` → quit cleanly
  - `H + Enter` → help

### 📊 Live Transfer Stats
- Per-file **percent complete**
- Per-file **speed (MB/s)**
- Per-file **ETA**
- **Overall batch progress**
  - Total percent
  - Total throughput (MB/s)
- **Very colorful ANSI output** (Windows Terminal / modern shells)

### 📝 Logging
Each run creates a timestamped log file containing:
- Full URL list sent to FBI
- Start/stop times
- Per-file transfer results
- Warnings vs hard failures

---

## 📦 Download

Grab the latest bundle from the repo releases or use the included ZIP:

