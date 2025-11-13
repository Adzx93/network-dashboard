import pandas as pd
import os
import time
from datetime import datetime, timedelta
from ftplib import FTP
from dotenv import load_dotenv
import json
import subprocess

# ---------------- CONFIG ----------------
CSV_FILE = "ping_log.csv"
HTML_FILE = "dashboard.html"
DASHBOARD_REFRESH = 60  # seconds

load_dotenv()
FTP_HOST = os.getenv("FTP_HOST")
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_PATH = os.getenv("FTP_PATH", "/dashboard.html")

# ---------------- FUNCTIONS ----------------

def generate_dashboard():
    if not os.path.exists(CSV_FILE):
        print("[WARNING] No log file found.")
        return

    # Load ping log
    df = pd.read_csv(CSV_FILE, names=["timestamp", "hostname", "ip", "status", "latency"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["latency"] = pd.to_numeric(df["latency"], errors="coerce")

    # Only keep last 7 days
    cutoff = datetime.now() - timedelta(days=7)
    df = df[df["timestamp"] > cutoff]

    dashboard_rows = []

    # Aggregate per host
    for (hostname, ip), group in df.groupby(["hostname", "ip"]):
        total = len(group)
        up_count = len(group[group["status"] == "UP"])
        uptime = round((up_count / total) * 100, 2) if total > 0 else 0

        avg_latency = group["latency"].mean()
        last_up_time = group[group["status"] == "UP"]["timestamp"].max()
        current_status = group.iloc[-1]["status"]

        dashboard_rows.append({
            "hostname": hostname,
            "ip": ip,
            "status": current_status,
            "uptime": uptime,
            "avg_latency": round(avg_latency, 1) if not pd.isna(avg_latency) else None,
            "last_up": last_up_time.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(last_up_time) else "—"
        })

    # Sort DOWN hosts to top
    dashboard_rows.sort(key=lambda x: 0 if x["status"]=="DOWN" else 1)

    # Generate HTML
    html = generate_html(dashboard_rows)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard updated locally: {HTML_FILE}")

    # Optional: upload to FTP
    upload_to_ftp(HTML_FILE)

    # Push to GitHub
    push_to_github(HTML_FILE)


def generate_html(rows):
    html = f"""
<html>
<head>
    <meta http-equiv="refresh" content="{DASHBOARD_REFRESH}">
    <title>Network Status Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #f8f9fa; color: #333; }}
        body.dark-mode {{ background: #121212; color: #fff; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        th {{ background: #007bff; color: white; }}
        body.dark-mode th {{ background: #1e88e5; color: #fff; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
        body.dark-mode tr:nth-child(even) {{ background: #1e1e1e; }}
        td, th {{ color: inherit; }}
        .UP {{ color: green; font-weight: bold; }}
        .DOWN {{ color: red; font-weight: bold; }}
        body.dark-mode .UP, body.dark-mode .DOWN {{ color: #fff; }}
        button {{ margin-top: 10px; padding: 5px 10px; cursor: pointer; }}
    </style>
</head>
<body>
    <button id="toggle-dark">Toggle Dark Mode</button>
    <h2>📊 Network Monitoring Dashboard</h2>
    <p>Last updated: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
    <table>
        <tr>
            <th>Hostname</th><th>IP</th><th>Status</th><th>Uptime (7d)</th><th>Avg Latency (ms)</th><th>Last Successful Ping</th>
        </tr>
"""
    for row in rows:
        html += f"""
        <tr>
            <td>{row['hostname']}</td>
            <td>{row['ip']}</td>
            <td class="{row['status']}">{'✅' if row['status']=='UP' else '❌'} {row['status']}</td>
            <td>{row['uptime']}%</td>
            <td>{row['avg_latency'] if row['avg_latency'] else '—'}</td>
            <td>{row['last_up']}</td>
        </tr>
        """
    html += "</table>"

    # Dark mode toggle script
    html += """
<script>
const toggleBtn = document.getElementById('toggle-dark');
const darkMode = localStorage.getItem('darkMode') === 'true';
if(darkMode){ document.body.classList.add('dark-mode'); }

toggleBtn.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
    localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
});
</script>
</body>
</html>
"""
    return html


def upload_to_ftp(file_path):
    if not FTP_HOST or not FTP_USER or not FTP_PASS:
        return
    try:
        with FTP(FTP_HOST) as ftp:
            ftp.login(FTP_USER, FTP_PASS)
            with open(file_path, "rb") as f:
                ftp.storbinary(f"STOR " + FTP_PATH, f)
        print(f"✅ Uploaded {file_path} to FTP server at {FTP_PATH}")
    except Exception as e:
        print(f"[ERROR] FTP upload failed: {e}")


def push_to_github(file_path):
    """Automatically commit and push updated HTML to GitHub Pages."""
    try:
        subprocess.run(["git", "add", file_path], check=True)
        subprocess.run(["git", "commit", "-m", "Update dashboard"], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        print(f"✅ Dashboard pushed to GitHub: {file_path}")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git push failed: {e}")


# ---------------- MAIN LOOP ----------------
if __name__ == "__main__":
    print(f"🔄 Starting continuous dashboard updates every {DASHBOARD_REFRESH}s...")
    while True:
        generate_dashboard()
        time.sleep(DASHBOARD_REFRESH)
