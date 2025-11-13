import pandas as pd
import os
import time
from datetime import datetime, timedelta

# ---------------- CONFIG ----------------
CSV_FILE = "ping_log.csv"
HTML_FILE = "dashboard.html"
DASHBOARD_REFRESH = 60  # seconds

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

    # Sort DOWN hosts to the top
    dashboard_rows.sort(key=lambda x: 0 if x["status"] == "DOWN" else 1)

    # Generate HTML
    html = generate_html(dashboard_rows)
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard generated locally: {HTML_FILE}")


def generate_html(rows):
    html = f"""
<html>
<head>
    <meta http-equiv="refresh" content="{DASHBOARD_REFRESH}">
    <title>Network Status Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #f8f9fa; color: #333; transition: all 0.3s; }}
        body.dark {{ background: #121212; color: #f0f0f0; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; transition: all 0.3s; color: inherit; }}
        th {{ background: #007bff; color: white; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
        body.dark tr:nth-child(even) {{ background: #1e1e1e; }}

        /* Status colors */
        .UP {{ color: green; font-weight: bold; }}
        .DOWN {{ color: red; font-weight: bold; }}

        /* Dark mode overrides */
        body.dark td:not(.UP):not(.DOWN) {{ color: white; }}  /* All non-UP/DOWN text white */
        body.dark .UP {{ color: #00ff00; }}                  /* Bright green for UP */
        body.dark .DOWN {{ color: #ff4444; }}               /* Bright red for DOWN */

        .toggle-container {{ margin-top: 10px; }}
    </style>
</head>
<body>
    <h2>📊 Network Monitoring Dashboard (Test)</h2>
    <p>Last updated: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
    <div class="toggle-container">
        <label><input type="checkbox" id="darkModeToggle"> Dark Mode</label>
    </div>
    <table>
        <tr>
            <th>Hostname</th><th>IP</th><th>Status</th><th>Uptime (7d)</th><th>Avg Latency (ms)</th><th>Last Successful Ping</th>
        </tr>
"""
    # Add table rows
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

    html += """
</table>
<script>
const toggle = document.getElementById('darkModeToggle');
const body = document.body;

// Initialize dark mode from localStorage
if(localStorage.getItem('darkMode') === 'true') {
    body.classList.add('dark');
    toggle.checked = true;
}

// Toggle dark mode
toggle.addEventListener('change', () => {
    if(toggle.checked) {
        body.classList.add('dark');
        localStorage.setItem('darkMode','true');
    } else {
        body.classList.remove('dark');
        localStorage.setItem('darkMode','false');
    }
});
</script>
</body>
</html>
"""
    return html


if __name__ == "__main__":
    generate_dashboard()
