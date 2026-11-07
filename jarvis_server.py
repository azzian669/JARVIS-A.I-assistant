"""
J.A.R.V.I.S. — LOCAL TELEMETRY SERVER
=======================================
Run this alongside jarvis_local.py (or import it from there).
Exposes a local API at http://localhost:5000 that the HUD polls.

Install: pip install flask flask-cors
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import psutil
import threading
import time
import datetime
import json
import os

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

HUD_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def serve_hud():
    """Open http://127.0.0.1:5000 in browser to get the HUD."""
    hud_path = os.path.join(HUD_DIR, 'jarvis_hud.html')
    if os.path.exists(hud_path):
        return send_file(hud_path)
    return "<h2>jarvis_hud.html not found.</h2>", 404

# ==========================================
# SHARED STATE — written by JARVIS, read by HUD
# ==========================================
jarvis_state = {
    "status":        "STANDBY",       # STANDBY / ACTIVE / THINKING / SPEAKING
    "mode_text":     "AWAITING COMMAND",
    "last_command":  "",
    "last_response": "",
    "wake_confidence": 0.0,
    "mic_active":    False,
    "tts_speaking":  False,
    "uptime_start":  time.time(),

    # Module online flags — set these from jarvis_local.py
    "modules": {
        "WAKE":   True,
        "TTS":    True,
        "MEM":    True,
        "LLM":    True,
        "VISION": False,
        "TEL":    False,
        "MAIL":   False,
        "PHONE":  False,
    },

    # Agent network
    "agents": {
        "CORE / PHI-3":    "ONLINE",
        "MEMORY / CHROMA": "ONLINE",
        "WAKE / OWW":      "STANDBY",
        "VISION / OCR":    "IDLE",
        "TELEGRAM":        "OFFLINE",
        "GMAIL":           "OFFLINE",
    },
}

# Log ring buffer — last 50 entries
log_buffer = []
log_lock   = threading.Lock()


def add_log(tag, level, message):
    """
    Add a log entry. level = 'ok' | 'warn' | 'info' | 'cmd' | 'error'
    Call this from anywhere in JARVIS to push entries to the HUD.
    """
    with log_lock:
        entry = {
            "time":    datetime.datetime.now().strftime("%H:%M:%S"),
            "tag":     tag,
            "level":   level,
            "message": message,
        }
        log_buffer.append(entry)
        if len(log_buffer) > 50:
            log_buffer.pop(0)


def set_status(status, mode_text=""):
    """Update JARVIS arc reactor status."""
    jarvis_state["status"]    = status
    if mode_text:
        jarvis_state["mode_text"] = mode_text


def set_command(command, response=""):
    """Record the latest command + response."""
    jarvis_state["last_command"]  = command
    jarvis_state["last_response"] = response


def set_wake_confidence(conf):
    jarvis_state["wake_confidence"] = round(conf, 3)


def set_module(name, active: bool):
    if name in jarvis_state["modules"]:
        jarvis_state["modules"][name] = active


def set_agent(name, status):
    jarvis_state["agents"][name] = status


# ==========================================
# API ENDPOINTS
# ==========================================

@app.route("/api/state")
def api_state():
    """Full JARVIS state snapshot — polled every 2s by the HUD."""
    cpu  = psutil.cpu_percent(interval=0)
    ram  = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent

    # CPU temp (Windows — may return None if sensor unavailable)
    cpu_temp = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                if entries:
                    cpu_temp = round(entries[0].current, 1)
                    break
    except Exception:
        cpu_temp = None

    uptime_secs = int(time.time() - jarvis_state["uptime_start"])

    return jsonify({
        "telemetry": {
            "cpu":      round(cpu, 1),
            "ram":      round(ram, 1),
            "disk":     round(disk, 1),
            "cpu_temp": cpu_temp,
        },
        "status":          jarvis_state["status"],
        "mode_text":       jarvis_state["mode_text"],
        "last_command":    jarvis_state["last_command"],
        "last_response":   jarvis_state["last_response"],
        "wake_confidence": jarvis_state["wake_confidence"],
        "mic_active":      jarvis_state["mic_active"],
        "tts_speaking":    jarvis_state["tts_speaking"],
        "uptime_secs":     uptime_secs,
        "modules":         jarvis_state["modules"],
        "agents":          jarvis_state["agents"],
    })


@app.route("/api/logs")
def api_logs():
    """Return recent log entries."""
    since = request.args.get("since", 0, type=int)
    with log_lock:
        entries = log_buffer[since:]
    return jsonify({"logs": entries, "total": len(log_buffer)})


@app.route("/api/command", methods=["POST"])
def api_command():
    """
    Accept a text command from the HUD and return JARVIS response.
    The HUD sends: { "command": "open youtube" }
    """
    data = request.get_json(silent=True) or {}
    cmd  = data.get("command", "").strip()
    if not cmd:
        return jsonify({"error": "No command provided"}), 400

    add_log("[CMD]", "cmd", f'"{cmd}" — received from HUD')

    # Import route_command from your main JARVIS file if running together
    # Otherwise returns a placeholder so the HUD still works standalone
    try:
        from jarvis_local import route_command
        response, routed = route_command(cmd)
    except ImportError:
        response = f"[HUD MODE] Command received: {cmd}. Start JARVIS to execute."
        routed   = False

    set_command(cmd, response)
    add_log("[OK]" if routed else "[LLM]", "ok" if routed else "info", response[:120])

    return jsonify({"response": response, "routed": routed})


@app.route("/api/ping")
def api_ping():
    return jsonify({"alive": True, "version": "3.2"})


# ==========================================
# STARTUP — run server in background thread
# ==========================================
def start_server(port=5000):
    """Call this from jarvis_local.py to start the API in the background."""
    def _run():
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)   # Suppress Flask request noise
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    print(f"[SERVER] HUD API online → http://127.0.0.1:{port}")
    add_log("[OK]", "ok", f"Telemetry server online at port {port}.")


# ==========================================
# STANDALONE TEST
# Run `python jarvis_server.py` to test the API without JARVIS
# ==========================================
if __name__ == "__main__":
    print("[TEST MODE] Starting JARVIS telemetry server standalone...")
    add_log("[OK]",  "ok",   "J.A.R.V.I.S. v3.2 initialization sequence complete.")
    add_log("[OK]",  "ok",   "ChromaDB persistent memory online.")
    add_log("[OK]",  "ok",   "Phi-3 model loaded via Ollama.")
    add_log("[OK]",  "ok",   "openWakeWord engine calibrated.")
    add_log("[INFO]","info", "pyttsx3 TTS active.")
    add_log("[WARN]","warn", "Telegram agent not connected.")
    add_log("[WARN]","warn", "Gmail agent not configured.")
    add_log("[OK]",  "ok",   "HUD API ready. Open jarvis_hud.html in browser.")

    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)
    app.run(host="127.0.0.1", port=5000, debug=False)