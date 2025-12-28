#!/usr/bin/env python3
# servefiles_enhanced_v4.py
#
# v4 changes (per request):
# ✅ Maintain a history of previously used 3DS IPs
# ✅ On startup, present a selectable list so you don't have to re-type
#
# Keeps everything from v3:
# - Colorful output (ANSI)
# - Tolerant / fire-and-forget URL push (ACK is non-fatal)
# - Hotkeys: R=re-send URLs, Q=quit, H=help
# - Per-file progress (%, MB/s, ETA) + batch progress
# - Logging (includes URL list)
#
# Limitations:
# FBI URL receive protocol does NOT report install success/failure back to PC.

import argparse
import http.server
import os
import socket
import socketserver
import struct
import sys
import threading
import time
from urllib.parse import quote
from datetime import datetime

ACCEPTED_EXT = ('.cia', '.tik', '.cetk', '.3dsx')
DEFAULT_HOST_PORT = 8080
FBI_URL_RECEIVER_PORT = 5000

# ----------------- Color / console helpers -----------------

ANSI = True

def _enable_windows_vt():
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)) == 0:
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if kernel32.SetConsoleMode(h, new_mode) == 0:
            return False
        return True
    except Exception:
        return False

if os.name == "nt":
    _enable_windows_vt()

def cc(s, *codes):
    if not ANSI:
        return s
    return f"\x1b[{';'.join(codes)}m{s}\x1b[0m"

BOLD="1"
DIM="2"
RED="31"
GREEN="32"
YELLOW="33"
BLUE="34"
MAGENTA="35"
CYAN="36"
WHITE="37"
GRAY="90"

def banner():
    print(cc("╔══════════════════════════════════════════════════════════════╗", CYAN, BOLD))
    print(cc("║            FBI Remote Install Server  •  Enhanced v4         ║", CYAN, BOLD))
    print(cc("║   Colorful • IP History Picker • Re-send hotkey • Batch UI    ║", CYAN, BOLD))
    print(cc("╚══════════════════════════════════════════════════════════════╝", CYAN, BOLD))

# ----------------- IP History -----------------

def history_path():
    # Store beside this script (portable for GitHub ZIP users)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "ip_history.json")

def load_ip_history():
    p = history_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data if isinstance(x, str)]
    except Exception:
        pass
    return []

def save_ip_history(ips):
    p = history_path()
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ips, f, indent=2)
    except Exception:
        pass

_ipv4_re = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

def is_valid_ipv4(ip):
    if not _ipv4_re.match(ip.strip()):
        return False
    parts = ip.strip().split(".")
    return all(0 <= int(p) <= 255 for p in parts)

def pick_3ds_ip_interactive():
    ips = load_ip_history()
    print(cc("3DS IP selection:", BLUE, BOLD))
    if ips:
        print(cc("Previously used:", GRAY))
        for i, ip in enumerate(ips[:10], 1):
            print(cc(f"  {i}) ", YELLOW, BOLD) + cc(ip, MAGENTA, BOLD))
        print(cc("Enter a number to select, or type a new IP.", GRAY))
        prompt = cc("3DS IP (Enter = use #1): ", CYAN, BOLD)
    else:
        print(cc("No saved IPs yet.", GRAY))
        prompt = cc("Type the 3DS IP address: ", CYAN, BOLD)

    while True:
        raw = input(prompt).strip()
        if raw == "" and ips:
            chosen = ips[0]
            break
        if raw.isdigit() and ips:
            idx = int(raw)
            if 1 <= idx <= min(10, len(ips)):
                chosen = ips[idx-1]
                break
            print(cc("Invalid selection number.", RED, BOLD))
            continue
        if is_valid_ipv4(raw):
            chosen = raw
            break
        print(cc("Please enter a valid IPv4 address (example: 192.168.1.76).", RED, BOLD))

    # update history: chosen becomes most recent; keep max 20
    new_list = [chosen] + [ip for ip in ips if ip != chosen]
    new_list = new_list[:20]
    save_ip_history(new_list)
    return chosen

# ----------------- Networking helpers -----------------

def detect_host_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 53))
        return s.getsockname()[0]
    finally:
        try: s.close()
        except Exception: pass

def fmt_bytes(n):
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024 or unit == 'TB':
            return f"{n:.2f} {unit}" if unit != 'B' else f"{int(n)} {unit}"
        n /= 1024.0

def now_stamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# ----------------- Progress tracking -----------------

class ProgressState:
    def __init__(self, total_batch_bytes, total_files, log_write):
        self.total_batch_bytes = total_batch_bytes
        self.total_files = total_files
        self.log_write = log_write
        self.lock = threading.Lock()
        self.batch_sent = 0
        self.file_index_map = {}

    def set_file_index_map(self, urls):
        with self.lock:
            for i, u in enumerate(urls, 1):
                fn = u.split("/")[-1]
                self.file_index_map[fn] = i

    def add_batch(self, inc):
        with self.lock:
            self.batch_sent += inc
            return self.batch_sent

# ----------------- HTTP server handler -----------------

STATE_CHUNK_SIZE = 256 * 1024
STATE_BATCH_START = time.time()
STATE = None

class ProgressHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def copyfile(self, source, outputfile):
        try:
            total = os.fstat(source.fileno()).st_size
        except Exception:
            total = 0

        client_ip = self.client_address[0]
        filename = self.path.lstrip('/')

        sent = 0
        start = time.time()
        last_print = 0.0
        chunk = STATE_CHUNK_SIZE

        try:
            while True:
                data = source.read(chunk)
                if not data:
                    break
                outputfile.write(data)
                sent += len(data)
                batch_sent = STATE.add_batch(len(data))

                t = time.time()
                if total > 0 and (t - last_print) >= 0.10:
                    elapsed = max(t - start, 0.001)
                    speed = sent / elapsed
                    pct = (sent / total) * 100.0
                    eta = (total - sent) / speed if speed > 0 else 0.0

                    batch_pct = (batch_sent / STATE.total_batch_bytes) * 100.0 if STATE.total_batch_bytes > 0 else 0.0
                    batch_speed = batch_sent / max((t - STATE_BATCH_START), 0.001)

                    fn_idx = STATE.file_index_map.get(filename, None)
                    idx_txt = f"{fn_idx}/{STATE.total_files}" if fn_idx else f"?/{STATE.total_files}"

                    line = (
                        cc(f"{client_ip}", MAGENTA, BOLD) +
                        cc("  ►  ", GRAY) +
                        cc(f"{filename}", CYAN, BOLD) +
                        cc(" | ", GRAY) +
                        cc(f"File {idx_txt}", BLUE, BOLD) +
                        cc(" | ", GRAY) +
                        cc(f"{pct:6.2f}%", GREEN, BOLD) +
                        cc(" | ", GRAY) +
                        cc(f"{speed/1024/1024:6.2f} MB/s", YELLOW, BOLD) +
                        cc(" | ", GRAY) +
                        cc(f"ETA {eta:5.1f}s", WHITE, BOLD) +
                        cc(" || ", GRAY) +
                        cc("Batch ", GRAY) +
                        cc(f"{batch_pct:6.2f}%", GREEN, BOLD) +
                        cc(" @ ", GRAY) +
                        cc(f"{batch_speed/1024/1024:6.2f} MB/s", YELLOW, BOLD)
                    )
                    sys.stdout.write("\r" + line + " " * 10)
                    sys.stdout.flush()
                    last_print = t

            if total > 0:
                sys.stdout.write("\r" + " " * 160 + "\r")
                sys.stdout.flush()

            elapsed = max(time.time() - start, 0.001)
            avg = sent / elapsed
            fn_idx = STATE.file_index_map.get(filename, None)
            idx_txt = f"{fn_idx}/{STATE.total_files}" if fn_idx else f"?/{STATE.total_files}"

            print(
                cc("✔ ", GREEN, BOLD) +
                cc(f"{client_ip}", MAGENTA, BOLD) +
                cc("  ►  ", GRAY) +
                cc(f"{filename}", CYAN, BOLD) +
                cc(" | ", GRAY) +
                cc(f"File {idx_txt}", BLUE, BOLD) +
                cc(" | ", GRAY) +
                cc("DONE", GREEN, BOLD) +
                cc(" | ", GRAY) +
                cc(f"avg {avg/1024/1024:.2f} MB/s", YELLOW, BOLD) +
                cc(" | ", GRAY) +
                cc(f"{fmt_bytes(sent)}", WHITE, BOLD)
            )

        except Exception as e:
            print(cc("✖ ", RED, BOLD) + cc(f"{client_ip} -> {filename} | {e}", RED, BOLD))
            raise

class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

# ----------------- URL building + sending -----------------

def collect_files(target_path):
    target_path = target_path.strip()
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"{target_path}: No such file or directory.")

    if os.path.isfile(target_path):
        if not target_path.lower().endswith(ACCEPTED_EXT):
            raise ValueError(f"Unsupported file extension. Supported: {ACCEPTED_EXT}")
        return os.path.dirname(target_path) or ".", [os.path.basename(target_path)]
    else:
        directory = target_path
        files = [fn for fn in sorted(next(os.walk(target_path))[2]) if fn.lower().endswith(ACCEPTED_EXT)]
        if not files:
            raise ValueError("No supported files to serve in that directory.")
        return directory, files

def build_urls(host_ip, host_port, files):
    base_url = f"{host_ip}:{host_port}/"
    return [base_url + quote(fn) for fn in files]

def push_urls_once(target_ip, payload_bytes, connect_timeout=10, ack_wait=2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(connect_timeout)
    try:
        sock.connect((target_ip, FBI_URL_RECEIVER_PORT))
        sock.sendall(struct.pack('!L', len(payload_bytes)) + payload_bytes)
        delivered = True

        acked = False
        sock.settimeout(0.25)
        start = time.time()
        while time.time() - start < ack_wait:
            try:
                b = sock.recv(1)
                if b:
                    acked = True
                    break
            except socket.timeout:
                pass
            time.sleep(0.05)

        return delivered, acked, None
    except Exception as e:
        return False, False, str(e)
    finally:
        try: sock.close()
        except Exception: pass

def push_urls_with_retries(target_ip, payload_bytes, retries, retry_delay, connect_timeout, ack_wait):
    last_err = None
    for _ in range(max(1, retries)):
        delivered, acked, err = push_urls_once(target_ip, payload_bytes, connect_timeout=connect_timeout, ack_wait=ack_wait)
        if delivered:
            return True, acked, None
        last_err = err
        time.sleep(max(0.1, retry_delay))
    return False, False, last_err

# ----------------- Keyboard control -----------------

def control_thread(send_fn, stop_fn):
    help_txt = (
        cc("[Controls] ", CYAN, BOLD) +
        cc("R", YELLOW, BOLD) + cc(" = re-send URLs, ", GRAY) +
        cc("Q", YELLOW, BOLD) + cc(" = quit, ", GRAY) +
        cc("H", YELLOW, BOLD) + cc(" = help", GRAY)
    )
    print(help_txt)
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                time.sleep(0.2)
                continue
            cmd = line.strip().lower()
            if cmd in ("r", "re", "resend"):
                print(cc("↻ Re-sending URL list to FBI…", YELLOW, BOLD))
                send_fn()
            elif cmd in ("q", "quit", "exit"):
                print(cc("Stopping server…", RED, BOLD))
                stop_fn()
                return
            elif cmd in ("h", "help", "?"):
                print(help_txt)
        except Exception:
            time.sleep(0.2)

# ----------------- Main -----------------

def main():
    global STATE_BATCH_START, STATE, STATE_CHUNK_SIZE

    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".", help="File or directory to send/serve (default .)")
    ap.add_argument("--3ds-ip", dest="target_ip", default=None, help="3DS IP (if omitted, you'll pick from history / enter manually)")
    ap.add_argument("host_ip", nargs="?", default=None, help="Host IP (default: auto-detect)")
    ap.add_argument("host_port", nargs="?", type=int, default=DEFAULT_HOST_PORT, help=f"Host port (default {DEFAULT_HOST_PORT})")
    ap.add_argument("--no-send", action="store_true", help="Only run HTTP server; do not push URLs to FBI.")
    ap.add_argument("--retries", type=int, default=5, help="Retries for URL push if connect/send fails (default 5)")
    ap.add_argument("--retry-delay", type=float, default=1.0, help="Seconds between URL push retries (default 1.0)")
    ap.add_argument("--connect-timeout", type=float, default=10.0, help="TCP connect timeout seconds (default 10)")
    ap.add_argument("--ack-wait", type=float, default=2.0, help="Seconds to briefly wait for ACK (default 2.0; non-fatal)")
    ap.add_argument("--chunk-kb", type=int, default=256, help="HTTP file chunk size KB (default 256)")
    args = ap.parse_args()

    STATE_CHUNK_SIZE = max(16, args.chunk_kb) * 1024
    host_ip = args.host_ip or detect_host_ip()

    # Choose target IP
    target_ip = args.target_ip
    if not target_ip:
        target_ip = pick_3ds_ip_interactive()
    elif not is_valid_ipv4(target_ip):
        print(cc("Error: ", RED, BOLD) + cc("Invalid --3ds-ip", RED, BOLD))
        return 2

    log_name = f"servefiles_log_v4_{now_stamp()}.txt"
    log_path = os.path.abspath(log_name)

    def log_write(line):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {line}\n")

    # Collect files and compute batch size
    try:
        directory, files = collect_files(args.path)
    except Exception as e:
        print(cc("Error: ", RED, BOLD) + str(e))
        return 1

    total_bytes = 0
    for fn in files:
        p = os.path.join(directory, fn)
        try:
            total_bytes += os.path.getsize(p)
        except Exception:
            pass

    urls = build_urls(host_ip, args.host_port, files)
    payload = "\n".join(urls).encode("ascii")

    if directory and directory != ".":
        os.chdir(directory)

    banner()
    print(cc("3DS IP      : ", GRAY) + cc(target_ip, MAGENTA, BOLD))
    print(cc("Host IP     : ", GRAY) + cc(host_ip, MAGENTA, BOLD))
    print(cc("Host Port   : ", GRAY) + cc(str(args.host_port), MAGENTA, BOLD))
    print(cc("Serving dir : ", GRAY) + cc(os.getcwd(), CYAN, BOLD))
    print(cc("Chunk size  : ", GRAY) + cc(f"{STATE_CHUNK_SIZE//1024} KB", YELLOW, BOLD))
    print(cc("Log file    : ", GRAY) + cc(log_path, GREEN, BOLD))
    print(cc("Files       : ", GRAY) + cc(f"{len(files)}", BLUE, BOLD) + cc(" | ", GRAY) + cc(f"{fmt_bytes(total_bytes)}", WHITE, BOLD))
    print(cc("IP history  : ", GRAY) + cc(os.path.abspath(history_path()), BLUE, BOLD))
    print()

    log_write(f"START v4 | 3DS={target_ip} | HOST={host_ip}:{args.host_port} | DIR={os.getcwd()} | FILES={len(files)} | BYTES={total_bytes}")
    log_write("URL LIST:")
    for u in urls:
        log_write("  http://" + u)

    # Init global state
    STATE_BATCH_START = time.time()
    STATE = ProgressState(total_bytes, len(files), log_write)
    STATE.set_file_index_map(urls)

    # Start HTTP server
    httpd = ThreadingTCPServer(("", args.host_port), ProgressHTTPRequestHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(cc("HTTP server: ", GRAY) + cc("RUNNING", GREEN, BOLD) + cc(" (waiting for FBI downloads)", GRAY))
    log_write("HTTP server started")

    def do_send():
        delivered, acked, err = push_urls_with_retries(
            target_ip,
            payload,
            retries=max(1, args.retries),
            retry_delay=max(0.1, args.retry_delay),
            connect_timeout=max(0.1, args.connect_timeout),
            ack_wait=max(0.0, args.ack_wait),
        )
        if delivered:
            if acked:
                print(cc("✔ URL list delivered (ACK received).", GREEN, BOLD))
                log_write("URL PUSH: delivered (ACK received)")
            else:
                print(cc("⚠ URL list delivered (no ACK).", YELLOW, BOLD) + cc("  (This is usually fine.)", GRAY))
                log_write("URL PUSH: delivered (no ACK)")
        else:
            print(cc("✖ URL push failed: ", RED, BOLD) + cc(str(err), RED))
            print(cc("  Server is still running. Start FBI 'Receive URLs…' and type R + Enter to retry.", GRAY))
            log_write(f"URL PUSH FAIL: {err}")

    def stop_all():
        try:
            httpd.shutdown()
        except Exception:
            pass

    if not args.no_send:
        print(cc("Sending URL list to FBI…", BLUE, BOLD))
        do_send()
    else:
        print(cc("NOTE: --no-send enabled (not pushing URLs).", YELLOW, BOLD))

    ctl = threading.Thread(target=control_thread, args=(do_send, stop_all), daemon=True)
    ctl.start()

    print()
    print(cc("On your 3DS: ", GRAY) + cc("FBI → Remote Install → Receive URLs over the network", CYAN, BOLD))
    print(cc("Tip: ", GRAY) + cc("Type ", GRAY) + cc("R", YELLOW, BOLD) + cc(" + Enter to re-send URLs anytime.", GRAY))
    print(cc("Stop: ", GRAY) + cc("Type ", GRAY) + cc("Q", YELLOW, BOLD) + cc(" + Enter to quit.", GRAY))
    print()

    try:
        while server_thread.is_alive():
            time.sleep(0.25)
    except KeyboardInterrupt:
        print(cc("\nCtrl+C received — stopping…", RED, BOLD))
    finally:
        stop_all()
        log_write("STOP v4")
        print(cc("Done.", GREEN, BOLD))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
