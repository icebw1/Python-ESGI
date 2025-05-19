import socket
import json
import os
import subprocess
import re
import platform
from datetime import datetime

FICHIER_CONNEXIONS = 'connexions.json'
FICHIER_BANS = 'bans.log'
HOST = '0.0.0.0'
PORT = 22
LIMITE_CONNEXIONS = 3

if os.path.exists(FICHIER_CONNEXIONS):
    with open(FICHIER_CONNEXIONS, 'r') as f:
        connexions = json.load(f)
else:
    connexions = {}

def ip_deja_bannie(ip):
    if not os.path.exists(FICHIER_BANS):
        return False
    with open(FICHIER_BANS, 'r') as f:
        return any(ip == line.strip().split(' - ')[1].split(' [')[0] for line in f if ' - ' in line)

def estimer_os_par_ttl(ttl):
    try:
        ttl = int(ttl)
        if ttl >= 128:
            return "Windows"
        elif ttl >= 64:
            return "Linux/macOS"
        elif ttl >= 255:
            return "Cisco/Unix"
        else:
            return "Inconnu"
    except:
        return "Inconnu"

def detecter_os(ip):
    system = platform.system()
    if system == "Windows":
        cmd = ["ping", "-n", "1", "-w", "1000", ip]  # -w en ms
    elif system == "Darwin":
        cmd = ["ping", "-c", "1", "-W", "1000", ip]  # -W en ms (macOS)
    else:  # Linux
        cmd = ["ping", "-c", "1", "-W", "1", ip]     # -W en s (Linux)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        match = re.search(r'ttl=(\d+)', result.stdout, re.IGNORECASE)
        if match:
            return estimer_os_par_ttl(match.group(1))
        return "Windows?"
    except Exception:
        return "Windows?"

def bloquer_ip_linux(ip):
    try:
        subprocess.run(["iptables", "-A", "INPUT", "-s", ip, "-j", "DROP"], check=True)
        print(f"IP {ip} bloquée via iptables.")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors du bannissement de {ip} : {e}")

def bloquer_ip_windows(ip):
    cmd = [
        "powershell",
        "-Command",
        f'New-NetFirewallRule -DisplayName "Block {ip}" -Direction Inbound -RemoteAddress {ip} -Action Block'
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"IP {ip} bloquée via Windows Firewall.")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors du bannissement de {ip} sous Windows : {e}")

def bloquer_ip_macos(ip):
    # Exemple simple pour bloquer via pfctl, nécessite config pf rules persistante pour être efficace
    rule = f"block drop from {ip} to any"
    pf_conf_path = "/etc/pf.conf"
    try:
        with open("/tmp/block_ips.conf", "w") as f:
            f.write(rule + "\n")
        subprocess.run(["sudo", "pfctl", "-f", pf_conf_path], check=True)
        subprocess.run(["sudo", "pfctl", "-e"], check=True)
        print(f"IP {ip} bloquée via pfctl.")
    except Exception as e:
        print(f"Erreur lors du bannissement de {ip} sous macOS : {e}")

def bloquer_ip(ip):
    system = platform.system()
    if system == "Linux":
        bloquer_ip_linux(ip)
    elif system == "Windows":
        bloquer_ip_windows(ip)
    elif system == "Darwin":
        bloquer_ip_macos(ip)
    else:
        print(f"Système {system} non supporté pour le blocage IP.")

def enregistrer_ban(ip):
    if ip_deja_bannie(ip):
        return
    os_detecte = detecter_os(ip)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(FICHIER_BANS, 'a') as f:
        f.write(f"{timestamp} - {ip} [{os_detecte}]\n")
    bloquer_ip(ip)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()
    print(f"En écoute sur {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()
        ip = addr[0]
        connexions[ip] = connexions.get(ip, 0) + 1

        with open(FICHIER_CONNEXIONS, 'w') as f:
            json.dump(connexions, f)

        if connexions[ip] > LIMITE_CONNEXIONS:
            print(f"Connexion refusée pour {ip} (limite atteinte)")
            enregistrer_ban(ip)
        else:
            print(f"Connexion acceptée de {ip} ({connexions[ip]})")

        conn.close()