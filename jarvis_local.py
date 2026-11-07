import pyaudio
import numpy as np
import openwakeword
from openwakeword.model import Model
import speech_recognition as sr
import requests
import json
import chromadb
import psutil
import pygame
import threading
import sys
import time
import webbrowser
import subprocess
import os
import re

# ==========================================
# HUD SERVER — import and start
# ==========================================
try:
    from jarvis_server import (
        start_server, add_log, set_status, set_command,
        set_wake_confidence, set_module, set_agent
    )
    HUD_SERVER = True
except ImportError:
    HUD_SERVER = False
    def add_log(*a, **k): pass
    def set_status(*a, **k): pass
    def set_command(*a, **k): pass
    def set_wake_confidence(*a, **k): pass
    def set_module(*a, **k): pass
    def set_agent(*a, **k): pass
    print("[HUD] jarvis_server.py not found. HUD disabled.")

# ==========================================
# TTS ENGINE SETUP
# Choose ONE: pyttsx3 (zero install) or piper (higher quality offline)
# pip install pyttsx3
# ==========================================
try:
    import pyttsx3
    tts_engine = pyttsx3.init()
    tts_engine.setProperty('rate', 165)       # Speaking speed
    tts_engine.setProperty('volume', 1.0)

    # Try to find a deeper, more JARVIS-like voice
    voices = tts_engine.getProperty('voices')
    for voice in voices:
        if "david" in voice.name.lower() or "mark" in voice.name.lower() or "male" in voice.name.lower():
            tts_engine.setProperty('voice', voice.id)
            break

    TTS_AVAILABLE = True
    print("[TTS] pyttsx3 engine loaded.")
except ImportError:
    TTS_AVAILABLE = False
    print("[TTS] pyttsx3 not found. Install with: pip install pyttsx3")

# TTS lock to prevent overlapping speech
tts_lock = threading.Lock()

def speak(text):
    """Speak text aloud. Non-blocking via thread."""
    if not TTS_AVAILABLE:
        print(f"[VOICE] {text}")
        return

    def _speak():
        with tts_lock:
            # Strip markdown and special characters for cleaner speech
            clean = re.sub(r'[\*\#\[\]\(\)\`]', '', text)
            clean = re.sub(r'\[.*?\]', '', clean)       # Remove telemetry tags
            clean = clean.strip()
            tts_engine.say(clean)
            tts_engine.runAndWait()

    t = threading.Thread(target=_speak, daemon=True)
    t.start()


# ==========================================
# 1. THE UI ENGINE (PyGame Multithreading)
# ==========================================

# Shared state for UI visual feedback
ui_state = {"active": False}  # True = JARVIS is thinking/speaking

def ui_thread():
    pygame.init()
    screen = pygame.display.set_mode((400, 400))
    pygame.display.set_caption("J.A.R.V.I.S. v3.2")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 13)
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((6, 8, 14))
        time_val = pygame.time.get_ticks() / 500

        # Outer decorative ring
        pygame.draw.circle(screen, (0, 60, 90), (200, 200), 110, 1)
        pygame.draw.circle(screen, (0, 40, 65), (200, 200), 130, 1)

        # Core pulsing sphere - cyan when active, dim when standby
        if ui_state["active"]:
            color = (0, 220, 255)
            radius = int(55 + 15 * abs(np.sin(time_val * 2)))
        else:
            color = (0, 100, 140)
            radius = int(48 + 6 * np.sin(time_val))

        pygame.draw.circle(screen, color, (200, 200), radius, 2)

        # Inner rings
        pygame.draw.circle(screen, (*color[:2], min(color[2], 80)), (200, 200), radius - 12, 1)
        pygame.draw.circle(screen, (*color[:2], 40), (200, 200), radius - 24, 1)

        # Status text
        status = "ACTIVE" if ui_state["active"] else "STANDBY"
        label = font.render(f"J.A.R.V.I.S. v3.2  |  {status}", True, (0, 180, 220))
        screen.blit(label, (200 - label.get_width() // 2, 330))

        # Telemetry overlay
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        tele = font.render(f"CPU {cpu:.0f}%   RAM {ram:.0f}%", True, (0, 100, 130))
        screen.blit(tele, (200 - tele.get_width() // 2, 350))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()

ui_process = threading.Thread(target=ui_thread, daemon=True)
ui_process.start()


# ==========================================
# 2. THE MEMORY ENGINE (ChromaDB)
# ==========================================
chroma_client = chromadb.PersistentClient(path="./jarvis_memory")
collection = chroma_client.get_or_create_collection(name="operator_logs")

def retrieve_memory(query_text):
    try:
        results = collection.query(query_texts=[query_text], n_results=3)
        if results['documents'] and results['documents'][0]:
            # Filter: only return memories with distance below threshold (relevant ones)
            docs = results['documents'][0]
            distances = results.get('distances', [[]])[0]
            relevant = [doc for doc, dist in zip(docs, distances) if dist < 1.2]
            return " | ".join(relevant) if relevant else ""
    except Exception:
        return ""
    return ""

def save_memory(query, response):
    try:
        doc_id = str(time.time())
        collection.add(
            documents=[f"Operator asked: {query}. J.A.R.V.I.S. answered: {response}"],
            ids=[doc_id]
        )
    except Exception as e:
        print(f"[MEMORY] Save failed: {e}")


# ==========================================
# 3. THE NERVOUS SYSTEM (Hardware Telemetry)
# ==========================================
def get_system_telemetry():
    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory().percent
    return f"[SYSTEM TELEMETRY: CPU @ {cpu}%, RAM @ {ram}%]"


# ==========================================
# 4. THE BRAIN (Ollama + Operator Profile)
# ==========================================
PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.txt")

DEFAULT_PERSONA = """
You are J.A.R.V.I.S., a local AI engineering assistant running on the operator's own machine.
Address the operator as "Sir". Be concise, analytical and dry-witted.
Keep spoken responses under 3 sentences where possible, because they are read aloud by a text-to-speech engine.
Ground explanations in practical engineering and, where relevant, live system telemetry.
"""

def load_persona():
    """Load a private persona from persona.txt (git-ignored) if present, else use the generic default."""
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text:
                return text
    except FileNotFoundError:
        pass
    return DEFAULT_PERSONA.strip()

SYSTEM_INSTRUCTION = load_persona()

def generate_response(user_input):
    print("\n[THINKING] Accessing local Phi-3 model...")
    ui_state["active"] = True

    context = retrieve_memory(user_input)
    telemetry = get_system_telemetry()

    augmented_prompt = f"{telemetry}\n"
    if context:
        augmented_prompt += f"[RECALLED MEMORY]: {context}\n"
    augmented_prompt += f"\nOperator Command: {user_input}"

    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "phi3",
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": augmented_prompt}
        ],
        "stream": False
    }

    try:
        response = requests.post(url, json=payload, timeout=60)
        reply = response.json()["message"]["content"]
        save_memory(user_input, reply)
        return reply
    except Exception as e:
        return f"Model connection failure. Error: {e}"
    finally:
        ui_state["active"] = False


# ==========================================
# 5. THE COMMAND ROUTER
# Rules-based fast lane. LLM is the fallback only.
# ==========================================

# App paths — adjust if needed
APP_PATHS = {
    "spotify":    r"C:\Users\{user}\AppData\Roaming\Spotify\Spotify.exe",
    "discord":    r"C:\Users\{user}\AppData\Local\Discord\app-*\Discord.exe",
    "vscode":     r"C:\Users\{user}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "notepad":    "notepad.exe",
    "calculator": "calc.exe",
    "explorer":   "explorer.exe",
}

def open_app(app_name):
    """Try to launch an application by name."""
    path = APP_PATHS.get(app_name)
    if path:
        try:
            # Resolve {user} in path
            path = path.format(user=os.environ.get("USERNAME", "User"))
            subprocess.Popen(path, shell=True)
            return True
        except Exception as e:
            print(f"[LAUNCHER] Failed to open {app_name}: {e}")
    return False

def route_command(command):
    """
    Fast command router. Intercepts known intents before hitting the LLM.
    Returns (response_text, routed) — routed=True means LLM was bypassed.
    """
    cmd = command.lower().strip()

    # --- SYSTEM STATUS ---
    if any(x in cmd for x in ["system status", "telemetry", "how's the system", "cpu", "ram usage"]):
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        return f"System nominal, sir. CPU at {cpu:.0f} percent, RAM at {ram:.0f} percent.", True

    # --- SHUTDOWN / SLEEP ---
    if any(x in cmd for x in ["shutdown", "power off", "go to sleep", "shut down"]):
        return "Initiating shutdown sequence.", True  # Handle externally

    # --- YOUTUBE ---
    if "open youtube" in cmd:
        webbrowser.open("https://youtube.com")
        return "Opening YouTube, sir.", True

    if ("play" in cmd or "search" in cmd) and "youtube" in cmd:
        query = re.sub(r'(play|search|on|youtube|for)', '', cmd).strip()
        if query:
            webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
            return f"Searching YouTube for {query}, sir.", True

    # --- SPOTIFY ---
    if "open spotify" in cmd:
        if open_app("spotify"):
            return "Launching Spotify, sir.", True
        webbrowser.open("https://open.spotify.com")
        return "Opening Spotify in browser, sir.", True

    if "play" in cmd and "spotify" in cmd:
        query = re.sub(r'(play|on|spotify)', '', cmd).strip()
        webbrowser.open(f"https://open.spotify.com/search/{query.replace(' ', '%20')}")
        return f"Searching Spotify for {query}, sir.", True

    # --- GOOGLE SEARCH ---
    if "google" in cmd or "search for" in cmd or "look up" in cmd:
        query = re.sub(r'(google|search for|look up|search)', '', cmd).strip()
        if query:
            webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
            return f"Searching Google for {query}, sir.", True

    # --- OPEN APPS ---
    if "open discord" in cmd:
        if open_app("discord"):
            return "Opening Discord, sir.", True

    if "open vs code" in cmd or "open vscode" in cmd:
        if open_app("vscode"):
            return "Launching VS Code, sir.", True

    if "open notepad" in cmd:
        open_app("notepad")
        return "Opening Notepad, sir.", True

    if "open calculator" in cmd or "open calc" in cmd:
        open_app("calculator")
        return "Calculator online, sir.", True

    if "open file explorer" in cmd or "open explorer" in cmd:
        open_app("explorer")
        return "Opening File Explorer, sir.", True

    # --- TIME ---
    if "what time" in cmd or "current time" in cmd:
        current_time = time.strftime("%I:%M %p")
        return f"Current time is {current_time}, sir.", True

    # --- DATE ---
    if "what's the date" in cmd or "today's date" in cmd or "what date" in cmd:
        current_date = time.strftime("%A, %B %d, %Y")
        return f"Today is {current_date}, sir.", True

    # --- VOLUME (Windows) ---
    if "volume up" in cmd:
        for _ in range(5):
            subprocess.call(["nircmd.exe", "changesysvolume", "3277"])  # Requires nircmd
        return "Volume increased, sir.", True

    if "volume down" in cmd:
        for _ in range(5):
            subprocess.call(["nircmd.exe", "changesysvolume", "-3277"])
        return "Volume decreased, sir.", True

    if "mute" in cmd:
        subprocess.call(["nircmd.exe", "mutesysvolume", "1"])
        return "System muted, sir.", True

    # --- FALLBACK TO LLM ---
    return generate_response(command), False


# ==========================================
# 6. THE ACTIVE EARS (Command Capture)
# ==========================================
recognizer = sr.Recognizer()

def capture_command():
    with sr.Microphone() as source:
        print("\n[LISTENING] Speak your command, sir...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=6, phrase_time_limit=12)
            command = recognizer.recognize_google(audio)
            print(f"\n  Operator: {command}")
            return command
        except sr.UnknownValueError:
            print("[ERROR] Audio unreadable. Returning to standby.")
            return None
        except sr.WaitTimeoutError:
            print("[ERROR] No speech detected. Returning to standby.")
            return None
        except sr.RequestError:
            print("[ERROR] Speech API unreachable.")
            return None


# ==========================================
# 7. THE WAKE WORD ENGINE (Main Loop)
# ==========================================
def main_standby_loop():
    print("\n" + "="*50)
    print("  J.A.R.V.I.S. v3.2 — SYSTEM ONLINE")
    print("="*50)
    print("  TTS     :", "pyttsx3 active" if TTS_AVAILABLE else "offline — text only")
    print("  Router  : Command routing layer active")
    print("  Memory  : ChromaDB persistent memory active")
    print("="*50)

    # Start HUD API server
    if HUD_SERVER:
        start_server(port=5000)
        add_log("[OK]",   "ok",   "J.A.R.V.I.S. v3.2 initialization complete.")
        add_log("[OK]",   "ok",   "ChromaDB persistent memory online.")
        add_log("[OK]",   "ok",   "Phi-3 model loaded via Ollama.")
        add_log("[OK]",   "ok",   "openWakeWord engine calibrated.")
        add_log("[INFO]", "info", f"pyttsx3 TTS: {'active' if TTS_AVAILABLE else 'unavailable'}.")
        add_log("[WARN]", "warn", "Telegram agent not connected.")
        add_log("[WARN]", "warn", "Gmail agent not configured.")
        add_log("[OK]",   "ok",   "HUD live — open jarvis_hud.html in browser.")
        set_status("STANDBY", "AWAITING COMMAND")

    speak("J.A.R.V.I.S. version 3.2 online. All systems nominal, sir.")

    oww_model = Model(wakeword_models=["jarvis"])

    FORMAT   = pyaudio.paInt16
    CHANNELS = 1
    RATE     = 16000
    CHUNK    = 1280

    audio      = pyaudio.PyAudio()
    mic_stream = audio.open(
        format=FORMAT, channels=CHANNELS, rate=RATE,
        input=True, frames_per_buffer=CHUNK
    )

    print("\n[STANDBY] Awaiting 'Jarvis' wake word...\n")

    try: 
        while True:
            audio_data = np.frombuffer(
                mic_stream.read(CHUNK, exception_on_overflow=False),
                dtype=np.int16
            )

            prediction = oww_model.predict(audio_data)
            score = prediction.get('jarvis', 0)

            if score > 0.1:
                print(f"[WAKE] confidence : {score:.3f}")

                if score > 0.5:
                 print("\n" + "="*50)
                print("  [WAKE WORD DETECTED] System Active.")
                print("="*50)
                ui_state["active"] = True
                set_status("ACTIVE", "PROCESSING...")
                mic_stream.stop_stream()

                command = capture_command()

                if command:
                    if any(x in command.lower() for x in ["shutdown jarvis", "power off jarvis", "exit"]):
                        speak("Powering down. Goodbye, sir.")
                        time.sleep(2)
                        mic_stream.close()
                        audio.terminate()
                        sys.exit()


                    response, was_routed = route_command(command)
                    source = "ROUTER" if was_routed else "PHI-3"
                    print(f"\n  [{source}] J.A.R.V.I.S.: {response}")
                    speak(response)
                    set_command(command, response)

                ui_state["active"] = False
                set_status("STANDBY", "AWAITING COMMAND")
                print("\n[RETURNING TO STANDBY]")
                mic_stream.start_stream()


    except KeyboardInterrupt:
        print("\n[SYSTEM SHUTDOWN] Ctrl+C detected. Powering off.")
        speak("Manual override detected. Shutting down.")
        time.sleep(2)
        mic_stream.close()
        audio.terminate()
        sys.exit()


if __name__ == "__main__":
    main_standby_loop()