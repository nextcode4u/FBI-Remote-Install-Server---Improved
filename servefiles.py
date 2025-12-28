#!/usr/bin/env python3
import argparse,http.server,os,socket,socketserver,struct,sys,threading,time,json,re
from urllib.parse import quote
from datetime import datetime

ACCEPTED_EXT=('.cia','.tik','.cetk','.3dsx')
DEFAULT_HOST_PORT=8080
FBI_URL_RECEIVER_PORT=5000

ANSI=True
BOLD,RED,GREEN,YELLOW,BLUE,MAGENTA,CYAN,WHITE,GRAY="1","31","32","33","34","35","36","37","90"

def _enable_windows_vt():
    try:
        import ctypes
        k=ctypes.windll.kernel32
        h=k.GetStdHandle(-11)
        mode=ctypes.c_uint32()
        if k.GetConsoleMode(h,ctypes.byref(mode))==0:return False
        return k.SetConsoleMode(h,mode.value|0x0004)!=0
    except Exception:
        return False

def _supports_ansi():
    if os.name!="nt": return True
    if os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM")=="vscode": return True
    return _enable_windows_vt()

ANSI=_supports_ansi()

def cc(s,*codes):
    if not ANSI:return s
    return f"\x1b[{';'.join(codes)}m{s}\x1b[0m"

def banner():
    print(cc("╔══════════════════════════════════════════════════════════════╗",CYAN,BOLD))
    print(cc("║                 FBI Remote Install Enhanced                  ║",CYAN,BOLD))
    print(cc("║      Colorful • IP History • Host IP Picker • Hotkeys         ║",CYAN,BOLD))
    print(cc("╚══════════════════════════════════════════════════════════════╝",CYAN,BOLD))

def history_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),"ip_history.json")

def load_ip_history():
    try:
        with open(history_path(),"r",encoding="utf-8") as f:
            data=json.load(f)
        if isinstance(data,list):
            return [str(x) for x in data if isinstance(x,str)]
    except Exception:
        pass
    return []

def save_ip_history(ips):
    try:
        with open(history_path(),"w",encoding="utf-8") as f:
            json.dump(ips,f,indent=2)
    except Exception:
        pass

_ipv4_re=re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
def is_valid_ipv4(ip):
    ip=ip.strip()
    if not _ipv4_re.match(ip): return False
    try:
        return all(0<=int(p)<=255 for p in ip.split("."))
    except Exception:
        return False

def pick_3ds_ip_interactive():
    ips=load_ip_history()
    print(cc("3DS IP:",BLUE,BOLD))
    if ips:
        for i,ip in enumerate(ips[:10],1):
            print(cc(f"  {i}) ",YELLOW,BOLD)+cc(ip,MAGENTA,BOLD))
        print(cc("Enter number, or type a new IP. Press Enter for #1.",GRAY))
        prompt=cc("3DS IP: ",CYAN,BOLD)
    else:
        prompt=cc("3DS IP: ",CYAN,BOLD)
    while True:
        raw=input(prompt).strip()
        if raw=="" and ips:
            chosen=ips[0];break
        if raw.isdigit() and ips:
            idx=int(raw)
            if 1<=idx<=min(10,len(ips)):
                chosen=ips[idx-1];break
            print(cc("Invalid selection.",RED,BOLD));continue
        if is_valid_ipv4(raw):
            chosen=raw;break
        print(cc("Enter a valid IPv4 address (example: 192.168.1.XX).",RED,BOLD))
    new_list=[chosen]+[ip for ip in ips if ip!=chosen]
    save_ip_history(new_list[:20])
    return chosen

def list_local_ipv4():
    ips=set()
    try:
        host=socket.gethostname()
        for fam,_,_,_,sockaddr in socket.getaddrinfo(host,None):
            if fam==socket.AF_INET:
                ip=sockaddr[0]
                if not ip.startswith("127."):
                    ips.add(ip)
    except Exception:
        pass
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(("8.8.8.8",53))
        ip=s.getsockname()[0]
        if ip and not ip.startswith("127."): ips.add(ip)
    except Exception:
        pass
    finally:
        try:s.close()
        except Exception:pass
    return sorted(ips)

def pick_host_ip_interactive(auto_ip):
    ips=list_local_ipv4()
    if not ips:
        return auto_ip
    if auto_ip and auto_ip not in ips:
        ips=[auto_ip]+ips
    print(cc("Host IP:",BLUE,BOLD))
    for i,ip in enumerate(ips[:10],1):
        tag=" (auto)" if ip==auto_ip else ""
        print(cc(f"  {i}) ",YELLOW,BOLD)+cc(ip,MAGENTA,BOLD)+cc(tag,GRAY))
    print(cc("Press Enter for the auto choice.",GRAY))
    while True:
        raw=input(cc("Host IP: ",CYAN,BOLD)).strip()
        if raw=="":
            return auto_ip if auto_ip else ips[0]
        if raw.isdigit():
            idx=int(raw)
            if 1<=idx<=min(10,len(ips)):
                return ips[idx-1]
        if is_valid_ipv4(raw):
            return raw
        print(cc("Invalid selection.",RED,BOLD))

def detect_host_ip():
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(('8.8.8.8',53))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        try:s.close()
        except Exception:pass

def fmt_bytes(n):
    n=float(n)
    for unit in ["B","KB","MB","GB","TB"]:
        if n<1024 or unit=="TB":
            return f"{int(n)} B" if unit=="B" else f"{n:.2f} {unit}"
        n/=1024.0

def now_stamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def logs_dir():
    d=os.path.join(os.path.dirname(os.path.abspath(__file__)),"logs")
    os.makedirs(d,exist_ok=True)
    return d

class ProgressState:
    def __init__(self,total_batch_bytes,total_files):
        self.total_batch_bytes=total_batch_bytes
        self.total_files=total_files
        self.lock=threading.Lock()
        self.batch_sent=0
        self.file_index_map={}
    def set_file_index_map(self,urls):
        with self.lock:
            for i,u in enumerate(urls,1):
                self.file_index_map[u.split("/")[-1]]=i
    def add_batch(self,inc):
        with self.lock:
            self.batch_sent+=inc
            return self.batch_sent

STATE_CHUNK_SIZE=256*1024
STATE_BATCH_START=time.time()
STATE=None

class ProgressHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,format,*args): return
    def copyfile(self,source,outputfile):
        try: total=os.fstat(source.fileno()).st_size
        except Exception: total=0
        client_ip=self.client_address[0]
        filename=self.path.lstrip('/')
        sent=0
        start=time.time()
        last=0.0
        chunk=STATE_CHUNK_SIZE
        while True:
            data=source.read(chunk)
            if not data: break
            outputfile.write(data)
            sent+=len(data)
            batch_sent=STATE.add_batch(len(data))
            t=time.time()
            if total>0 and (t-last)>=0.10:
                elapsed=max(t-start,0.001)
                speed=sent/elapsed
                pct=(sent/total)*100.0
                eta=(total-sent)/speed if speed>0 else 0.0
                batch_pct=(batch_sent/STATE.total_batch_bytes)*100.0 if STATE.total_batch_bytes>0 else 0.0
                batch_speed=batch_sent/max((t-STATE_BATCH_START),0.001)
                fn_idx=STATE.file_index_map.get(filename,None)
                idx_txt=f"{fn_idx}/{STATE.total_files}" if fn_idx else f"?/{STATE.total_files}"
                line=(cc(f"{client_ip}",MAGENTA,BOLD)+cc(" ► ",GRAY)+cc(filename,CYAN,BOLD)+cc(" | ",GRAY)+
                      cc(f"{idx_txt}",BLUE,BOLD)+cc(" | ",GRAY)+cc(f"{pct:6.2f}%",GREEN,BOLD)+cc(" | ",GRAY)+
                      cc(f"{speed/1024/1024:5.2f} MB/s",YELLOW,BOLD)+cc(" | ",GRAY)+cc(f"{eta:5.1f}s",WHITE,BOLD)+
                      cc(" || ",GRAY)+cc(f"{batch_pct:6.2f}%",GREEN,BOLD)+cc(" @ ",GRAY)+
                      cc(f"{batch_speed/1024/1024:5.2f} MB/s",YELLOW,BOLD))
                sys.stdout.write("\r"+line+" "*10);sys.stdout.flush();last=t
        if total>0:
            sys.stdout.write("\r"+" "*170+"\r");sys.stdout.flush()
        elapsed=max(time.time()-start,0.001)
        avg=sent/elapsed
        fn_idx=STATE.file_index_map.get(filename,None)
        idx_txt=f"{fn_idx}/{STATE.total_files}" if fn_idx else f"?/{STATE.total_files}"
        print(cc("✔ ",GREEN,BOLD)+cc(client_ip,MAGENTA,BOLD)+cc(" ► ",GRAY)+cc(filename,CYAN,BOLD)+cc(" | ",GRAY)+
              cc(f"{idx_txt}",BLUE,BOLD)+cc(" | ",GRAY)+cc("DONE",GREEN,BOLD)+cc(" | ",GRAY)+
              cc(f"{avg/1024/1024:.2f} MB/s",YELLOW,BOLD)+cc(" | ",GRAY)+cc(fmt_bytes(sent),WHITE,BOLD))

class ThreadingTCPServer(socketserver.ThreadingMixIn,socketserver.TCPServer):
    daemon_threads=True
    allow_reuse_address=True

def collect_files(target_path):
    target_path=target_path.strip()
    if not os.path.exists(target_path):
        raise FileNotFoundError(f"{target_path}: No such file or directory.")
    if os.path.isfile(target_path):
        if not target_path.lower().endswith(ACCEPTED_EXT):
            raise ValueError(f"Unsupported file extension. Supported: {ACCEPTED_EXT}")
        return os.path.dirname(target_path) or ".", [os.path.basename(target_path)]
    directory=target_path
    files=[fn for fn in sorted(next(os.walk(target_path))[2]) if fn.lower().endswith(ACCEPTED_EXT)]
    if not files: raise ValueError("No supported files to serve in that directory.")
    return directory, files

def build_urls(host_ip,host_port,files):
    base=f"{host_ip}:{host_port}/"
    return [base+quote(fn) for fn in files]

def push_urls_once(target_ip,payload,connect_timeout=10,ack_wait=2):
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.settimeout(connect_timeout)
    try:
        sock.connect((target_ip,FBI_URL_RECEIVER_PORT))
        sock.sendall(struct.pack('!L',len(payload))+payload)
        acked=False
        sock.settimeout(0.25)
        start=time.time()
        while time.time()-start<ack_wait:
            try:
                b=sock.recv(1)
                if b: acked=True;break
            except socket.timeout:
                pass
            time.sleep(0.05)
        return True,acked,None
    except Exception as e:
        return False,False,str(e)
    finally:
        try:sock.close()
        except Exception:pass

def push_urls_with_retries(target_ip,payload,retries,retry_delay,connect_timeout,ack_wait):
    last=None
    for _ in range(max(1,retries)):
        d,a,e=push_urls_once(target_ip,payload,connect_timeout,ack_wait)
        if d: return True,a,None
        last=e
        time.sleep(max(0.1,retry_delay))
    return False,False,last

def control_thread(send_fn,stop_fn):
    help_txt=(cc("[Controls] ",CYAN,BOLD)+cc("R",YELLOW,BOLD)+cc(" resend  ",GRAY)+cc("Q",YELLOW,BOLD)+
              cc(" quit  ",GRAY)+cc("H",YELLOW,BOLD)+cc(" help",GRAY))
    print(help_txt)
    while True:
        line=sys.stdin.readline()
        if not line:
            time.sleep(0.2);continue
        cmd=line.strip().lower()
        if cmd in ("r","resend"):
            print(cc("↻ Re-sending URLs…",YELLOW,BOLD));send_fn()
        elif cmd in ("q","quit","exit"):
            print(cc("Stopping…",RED,BOLD));stop_fn();return
        elif cmd in ("h","help","?"):
            print(help_txt)

def main():
    global STATE_BATCH_START,STATE,STATE_CHUNK_SIZE
    ap=argparse.ArgumentParser()
    ap.add_argument("path",nargs="?",default=".")
    ap.add_argument("--3ds-ip",dest="target_ip",default=None)
    ap.add_argument("--host-ip",dest="host_ip",default=None)
    ap.add_argument("--host-port",dest="host_port",type=int,default=DEFAULT_HOST_PORT)
    ap.add_argument("--no-send",action="store_true")
    ap.add_argument("--copy-only",action="store_true")
    ap.add_argument("--retries",type=int,default=5)
    ap.add_argument("--retry-delay",type=float,default=1.0)
    ap.add_argument("--connect-timeout",type=float,default=10.0)
    ap.add_argument("--ack-wait",type=float,default=2.0)
    ap.add_argument("--chunk-kb",type=int,default=256)
    args=ap.parse_args()
    STATE_CHUNK_SIZE=max(16,args.chunk_kb)*1024

    target_ip=args.target_ip or pick_3ds_ip_interactive()
    if not is_valid_ipv4(target_ip):
        print(cc("Invalid 3DS IP.",RED,BOLD));return 2

    auto_host=detect_host_ip()
    host_ip=args.host_ip or pick_host_ip_interactive(auto_host)

    try:
        directory,files=collect_files(args.path)
    except Exception as e:
        print(cc("Error: ",RED,BOLD)+str(e));return 1

    total_bytes=sum((os.path.getsize(os.path.join(directory,f)) for f in files if os.path.exists(os.path.join(directory,f))),0)
    urls=build_urls(host_ip,args.host_port,files)
    payload="\n".join(urls).encode("ascii")

    if directory and directory!=".": os.chdir(directory)

    log_path=os.path.join(logs_dir(),f"servefiles_log_{now_stamp()}.txt")
    def log_write(line):
        ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path,"a",encoding="utf-8") as f:
            f.write(f"[{ts}] {line}\n")

    banner()
    print(cc("3DS: ",GRAY)+cc(target_ip,MAGENTA,BOLD)+cc("  Host: ",GRAY)+cc(f"{host_ip}:{args.host_port}",MAGENTA,BOLD))
    print(cc("Dir: ",GRAY)+cc(os.getcwd(),CYAN,BOLD))
    print(cc("Files: ",GRAY)+cc(str(len(files)),BLUE,BOLD)+cc("  Size: ",GRAY)+cc(fmt_bytes(total_bytes),WHITE,BOLD))
    print(cc("Log: ",GRAY)+cc(log_path,GREEN,BOLD))
    print()

    log_write(f"START | 3DS={target_ip} | HOST={host_ip}:{args.host_port} | DIR={os.getcwd()} | FILES={len(files)} | BYTES={total_bytes}")
    for u in urls: log_write("URL http://"+u)

    STATE_BATCH_START=time.time()
    STATE=ProgressState(total_bytes,len(files))
    STATE.set_file_index_map(urls)

    httpd=ThreadingTCPServer(("",args.host_port),ProgressHTTPRequestHandler)
    st=threading.Thread(target=httpd.serve_forever,daemon=True);st.start()
    print(cc("HTTP: ",GRAY)+cc("RUNNING",GREEN,BOLD))
    def do_send():
        delivered,acked,err=push_urls_with_retries(target_ip,payload,args.retries,args.retry_delay,args.connect_timeout,args.ack_wait)
        if delivered:
            msg="✔ URLs sent (ACK)" if acked else "⚠ URLs sent (no ACK)"
            print(cc(msg,GREEN,BOLD) if acked else cc(msg,YELLOW,BOLD))
            log_write("URL_PUSH delivered" + (" ACK" if acked else " NO_ACK"))
        else:
            print(cc("✖ URL push failed: ",RED,BOLD)+cc(str(err),RED))
            print(cc("Server is still running. Start FBI 'Receive URLs…' then type R.",GRAY))
            log_write(f"URL_PUSH_FAIL {err}")
    def stop_all():
        try:httpd.shutdown()
        except Exception: pass

    if args.copy_only:
        print(cc("COPY-ONLY mode: ",YELLOW,BOLD)+cc("server is running but URLs were not pushed.",GRAY))
        print(cc("Open FBI and install locally after transferring, or press R to push URLs.",GRAY))
    elif not args.no_send:
        do_send()

    ctl=threading.Thread(target=control_thread,args=(do_send,stop_all),daemon=True);ctl.start()
    print(cc("3DS: ",GRAY)+cc("FBI → Remote Install → Receive URLs over the network",CYAN,BOLD))
    print(cc("Keys: ",GRAY)+cc("R",YELLOW,BOLD)+cc(" resend  ",GRAY)+cc("Q",YELLOW,BOLD)+cc(" quit",GRAY))
    print()
    try:
        while st.is_alive(): time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop_all();log_write("STOP");print(cc("Done.",GREEN,BOLD))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
