import subprocess
import platform
import concurrent.futures
import time
import os
import requests
import schedule
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 60))  # seconds
GRACE_PERIOD = 300  # 5 minutes in seconds

PING_PARAM = "-n" if platform.system().lower() == "windows" else "-c"

# Track host status
down_since = {}        # {ip: timestamp when first seen down}
alerted_down = {}      # {ip: True if a down alert was sent}
previous_status = {}   # {ip: True/False}

def ping_host(hostname, ip):
    """Ping a host 3 times; return True if reachable, False if all fail."""
    try:
        result = subprocess.run(
            [PING_PARAM, "5", ip] if platform.system().lower() != "windows" else ["ping", "-n", "5", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return hostname, ip, (result.returncode == 0)
    except Exception:
        return hostname, ip, False

def send_webhook_message(message):
    """Send a message to the webhook."""
    if not WEBHOOK_URL:
        print("[WARNING] No WEBHOOK_URL set in .env — skipping alert")
        return
    try:
        payload = {"text": message}
        response = requests.post(WEBHOOK_URL, json=payload)
        if response.status_code in (200, 201, 202, 204):
            print("✅ Alert sent successfully!")
        else:
            print(f"❌ Failed to send alert. Status code: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"[ERROR] Failed to send webhook: {e}")

def daily_summary(targets):
    """Send daily 09:00 summary of all hosts."""
    down_hosts = []
    up_hosts = []

    for hostname, ip in targets:
        if previous_status.get(ip, True):
            up_hosts.append(f"✅ {hostname} ({ip})")
        else:
            down_hosts.append(f"❌ {hostname} ({ip})")

    summary_lines = []
    if down_hosts:
        summary_lines.append("⚠️ **Daily Summary — Hosts DOWN:**")
        summary_lines.extend([f"- {h}" for h in down_hosts])
    if up_hosts:
        summary_lines.append("\n✅ Hosts UP:")
        summary_lines.extend([f"- {h}" for h in up_hosts])

    summary_text = "\n".join(summary_lines)
    send_webhook_message(f"📊 Daily Network Check (09:00):\n{summary_text}")

def monitor():
    # Load IP list
    with open("ips.txt") as f:
        targets = []
        for line in f:
            if line.strip() and "," in line:
                hostname, ip = line.strip().split(",", 1)
                targets.append((hostname.strip(), ip.strip()))

    global previous_status, alerted_down
    previous_status = {ip: True for _, ip in targets}
    alerted_down = {ip: False for _, ip in targets}

    # Schedule daily summary
    schedule.every().day.at("09:00").do(daily_summary, targets=targets)

    while True:
        print("\n--- Running check ---")
        now = time.time()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(lambda t: ping_host(*t), targets)

        for hostname, ip, is_up in results:
            if is_up:
                print(f"[OK] {hostname} ({ip}) is reachable")
                down_since.pop(ip, None)

                # Send recovery alert only if a down alert was sent before
                if alerted_down.get(ip, False):
                    send_webhook_message(f"✅ **RECOVERY:** {hostname} ({ip}) is back UP")
                    alerted_down[ip] = False

            else:
                print(f"[DOWN] {hostname} ({ip}) is unreachable")
                if ip not in down_since:
                    down_since[ip] = now  # record first time seen down

                # Send alert only if grace period passed and no alert yet
                if (now - down_since[ip] >= GRACE_PERIOD) and not alerted_down.get(ip, False):
                    send_webhook_message(f"🚨 **ALERT:** {hostname} ({ip}) has been DOWN for 5+ minutes")
                    alerted_down[ip] = True

            previous_status[ip] = is_up

        # Run scheduled jobs (daily summary at 09:00)
        schedule.run_pending()

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    monitor()
