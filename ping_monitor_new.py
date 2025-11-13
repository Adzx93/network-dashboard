import subprocess
import platform
import concurrent.futures
import time
import os
import requests
import schedule
from dotenv import load_dotenv
import csv

load_dotenv()

# ---------------- CONFIG ----------------
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))  # seconds
GRACE_PERIOD = 300  # 5 minutes
PING_COUNT = 5

PING_PARAM = "-n" if platform.system().lower() == "windows" else "-c"

# Track host status
down_since = {}        # {ip: timestamp when first seen down}
alerted_down = {}      # {ip: True if a down alert was sent}
previous_status = {}   # {ip: True/False}

LOG_FILE = "ping_log.csv"

# ---------------- FUNCTIONS ----------------

def ping_host(hostname, ip):
    """Ping a host multiple times; return status, latency, timestamp."""
    try:
        cmd = ["ping", PING_PARAM, str(PING_COUNT), ip]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        is_up = (result.returncode == 0)
        latency = None

        # Extract average latency
        if is_up:
            if platform.system().lower() == "windows":
                for line in result.stdout.splitlines():
                    if "Average" in line:
                        latency = int(line.split("Average =")[-1].replace("ms","").strip())
                        break
            else:
                for line in result.stdout.splitlines():
                    if "rtt min" in line or "round-trip" in line:
                        latency = float(line.split("=")[1].split("/")[1])
                        break

        return hostname, ip, is_up, latency, time.strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:
        print(f"[ERROR] Ping failed for {hostname} ({ip}): {e}")
        return hostname, ip, False, None, time.strftime("%Y-%m-%d %H:%M:%S")


def log_ping_result(hostname, ip, is_up, latency, timestamp):
    """Append ping result to CSV for dashboard."""
    try:
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, hostname, ip, "UP" if is_up else "DOWN", latency if latency is not None else ""])
    except Exception as e:
        print(f"[ERROR] Failed to log result for {hostname}: {e}")


def send_webhook_message(message):
    """Send alert to webhook (Slack, Teams, etc.)."""
    if not WEBHOOK_URL:
        return
    try:
        payload = {"text": message}
        response = requests.post(WEBHOOK_URL, json=payload)
        if response.status_code not in (200,201,202,204):
            print(f"[ERROR] Webhook failed with status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[ERROR] Webhook exception: {e}")


def daily_summary(targets):
    """Send a daily summary of all hosts."""
    down_hosts = []
    up_hosts = []

    for hostname, ip in targets:
        if previous_status.get(ip, True):
            up_hosts.append(f"✅ {hostname} ({ip})")
        else:
            down_hosts.append(f"❌ {hostname} ({ip})")

    summary = []
    if down_hosts:
        summary.append("⚠️ Daily Summary — Hosts DOWN:")
        summary.extend(down_hosts)
    if up_hosts:
        summary.append("\n✅ Hosts UP:")
        summary.extend(up_hosts)

    message = "📊 Daily Network Check (09:00):\n" + "\n".join(summary)
    send_webhook_message(message)


# ---------------- MONITOR LOOP ----------------

def monitor():
    # Load targets
    with open("ips.txt") as f:
        targets = []
        for line in f:
            if line.strip() and "," in line:
                hostname, ip = line.strip().split(",",1)
                targets.append((hostname.strip(), ip.strip()))

    if not targets:
        print("[ERROR] No targets found in ips.txt")
        return

    global previous_status, alerted_down
    previous_status = {ip: True for _, ip in targets}
    alerted_down = {ip: False for _, ip in targets}

    print(f"[INFO] Monitoring {len(targets)} hosts...")

    # Schedule daily summary
    schedule.every().day.at("09:00").do(daily_summary, targets=targets)

    while True:
        now = time.time()
        print(f"\n--- Running check at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(lambda t: ping_host(*t), targets)

        for hostname, ip, is_up, latency, timestamp in results:
            log_ping_result(hostname, ip, is_up, latency, timestamp)

            if is_up:
                print(f"[OK] {hostname} ({ip}) reachable, latency={latency}ms")
                down_since.pop(ip, None)

                if alerted_down.get(ip, False):
                    send_webhook_message(f"✅ **RECOVERY:** {hostname} ({ip}) is back UP")
                    alerted_down[ip] = False
            else:
                print(f"[DOWN] {hostname} ({ip}) unreachable")
                if ip not in down_since:
                    down_since[ip] = now

                if (now - down_since[ip] >= GRACE_PERIOD) and not alerted_down.get(ip, False):
                    send_webhook_message(f"🚨 **ALERT:** {hostname} ({ip}) has been DOWN for 5+ minutes")
                    alerted_down[ip] = True

            previous_status[ip] = is_up

        # Run scheduled tasks
        schedule.run_pending()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    monitor()
