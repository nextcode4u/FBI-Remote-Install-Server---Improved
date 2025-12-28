# FBI Remote Install Enhanced (v4)

A **colorful, tolerant** helper for **FBI → Remote Install → Receive URLs over the network**, with a big usability upgrade:

✅ **No hard-coded default IP**  
✅ Keeps a **history of your previously used 3DS IPs** and lets you **pick from a menu** next time  
✅ Still has the v3 goodies: live speed, % progress, ETA, batch progress, hotkey re-send, logs

---

## ✨ Features

- **IP History Picker**
  - First run: type your 3DS IP
  - Next runs: choose from a numbered list (press Enter to use the most recent)
  - Stored locally in: `ip_history.json` (same folder as the script)

- **Tolerant / Fire-and-forget URL push**
  - If FBI doesn’t ACK in time, it **warns** but keeps serving

- **Live stats (host-side)**
  - Per-file: % / MB/s / ETA
  - Batch: overall % / overall MB/s

- **Hotkeys**
  - `R + Enter` → re-send URLs (no restart)
  - `Q + Enter` → quit
  - `H + Enter` → help

- **Logs**
  - Every run creates a timestamped log that includes the URL list

---

## 📦 Bundle Contents

- `servefiles_enhanced_v4.py`
- `FBI_remote_install_enhanced_v4.bat` (Windows)
- `FBI_remote_install_enhanced_v4.sh` (Linux/macOS)

---

## ✅ Requirements

- Python 3.7+
- FBI installed on 3DS
- 3DS and PC on the same LAN
- Best color support:
  - Windows Terminal (recommended)
  - Most Linux/macOS terminals

---

## ▶️ Usage

### 1) On your 3DS
Open:
```
FBI → Remote Install → Receive URLs over the network
```
Leave that screen open.

### 2) Windows (drag & drop)
Drag a `.cia` OR a folder onto:
```
FBI_remote_install_enhanced_v4.bat
```

### 3) Linux/macOS
```bash
chmod +x FBI_remote_install_enhanced_v4.sh
./FBI_remote_install_enhanced_v4.sh /path/to/cia_or_folder
```

---

## ⚠️ Important limitation (FBI protocol)

FBI’s URL-receive protocol does **not** report install success/failure back to the PC.

This tool can confirm:
- the URL list was sent
- files were transferred (you’ll see progress + DONE lines)

It cannot confirm:
- “install failed due to space/ticket/etc.”

---

## 🔧 Optional config

You can tweak behavior in the wrapper scripts or run Python directly:

```bash
python servefiles_enhanced_v4.py "./cias" --ack-wait 1 --retries 3 --chunk-kb 256
```

Useful flags:
- `--ack-wait` (non-fatal ACK wait seconds)
- `--retries` / `--retry-delay`
- `--chunk-kb`

---

## 📝 IP History Notes

- Stored in `ip_history.json` next to the script
- Keeps up to 20 entries
- Most recent IP is at the top

To reset the list, delete `ip_history.json`.

---

## License

Same license as the upstream FBI servefiles workflow (see upstream repo / original license).
