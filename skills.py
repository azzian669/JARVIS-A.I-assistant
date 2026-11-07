import os
import pytesseract
import pyautogui
import psutil

# Set TESSERACT_CMD if Tesseract is not on your PATH
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")


# 1. Mesinnya (Python Function)
def kalkulator_tambah(a, b):
    return a + b

# 2. Buku Panduannya (JSON Schema untuk AI)
skill_kalkulator = {
    "name": "kalkulator_tambah",
    "description": "Gunakan ini untuk menjumlahkan dua angka.",
    "parameters": {
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "Angka pertama"},
            "b": {"type": "integer", "description": "Angka kedua"}
        },
        "required": ["a", "b"]
    }
}




# --- Isi dari skills.py ---
import re
import webbrowser
import pyautogui
import pytesseract

# Konfigurasi path Tesseract (sesuaikan dengan instalasi Windows Anda)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def parse_and_search(command):
    command = command.lower()
    # Bersihkan noise
    command = command.replace(" and ", " ").replace(" please ", " ").strip()
    
    # KONDISI 1: Ada kata "open" DAN "search" (Contoh: "open youtube search vanossgaming")
    if "open" in command and "search" in command:
        match = re.search(r"open (.*?) search (.*)", command)
        if match:
            target = match.group(1).strip()
            query = match.group(2).strip()
            if "youtube" in target:
                webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}")
            else:
                webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
            print(f"[ SKILL LOG: Mencari '{query}' di {target} ]")
            
    # KONDISI 2: HANYA ada kata "search" (Contoh: "search natal")
    elif "search" in command and "open" not in command:
        query = command.replace("search", "").strip()
        print(f"[ SKILL LOG: Melakukan pencarian web untuk '{query}' ]")
        webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
        
    # KONDISI 3: HANYA ada kata "open" (Contoh: "open youtube")
    elif "open" in command and "search" not in command:
        target = command.replace("open", "").strip()
        print(f"[ SKILL LOG: Membuka '{target}' ]")
        if "youtube" in target:
            webbrowser.open("https://www.youtube.com")
        else:
            webbrowser.open(f"https://www.google.com/search?q={target}")
            
    # 3. Jika hanya menyuruh "open" tanpa "search"
    else:
        match = re.search(r"open (.*)", command)
        if match:
            target_site = match.group(1).strip()
            print(f"[ SKILL LOG: Membuka '{target_site}' ]")
            
            if "youtube" in target_site:
                webbrowser.open("https://www.youtube.com")
            elif "google" in target_site:
                webbrowser.open("https://www.google.com")
            else:
                # Jika Anda menyuruh buka web aneh, kita lempar ke pencarian Google
                webbrowser.open(f"https://www.google.com/search?q={target_site}")

def adjust_volume(action):
    if "up" in action.lower() or "raise" in action.lower():
        pyautogui.press('volumeup', presses=5)  # Naik 10%
        print("Volume dinaikkan.")
    elif "down" in action.lower() or "lower" in action.lower():
        pyautogui.press('volumedown', presses=5) # Turun 10%
        print("Volume diturunkan.")
    pass

import ast
import operator

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}

def _safe_eval(node):
    """Evaluate +, -, *, / arithmetic only. Anything else raises ValueError."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")

def calculate_math(command):
    math_expression = re.sub(r'[^0-9+\-*/().]', '', command)
    
    if math_expression:
        try:
            result = _safe_eval(ast.parse(math_expression, mode="eval"))
            print(f"Hasil kalkulasi: {result}")
            return result
        except Exception:
            print("Kesalahan sintaks matematika.")
    else:
        print("Tidak ada operasi matematika yang terdeteksi.")
    pass

def scan_screen():
    print("Memindai layar...")
    # Menangkap layar saat ini
    screenshot = pyautogui.screenshot()
    
    # Mengekstrak teks dari gambar
    screen_text = pytesseract.image_to_string(screenshot)
    
    if screen_text.strip():
        print("Teks terdeteksi:")
        print(screen_text)
    else:
        print("Layar bersih. Tidak ada teks yang relevan untuk diekstrak.")
    pass

def check_system_status():
    # Mengambil sampel penggunaan CPU selama 1 detik
    cpu_usage = psutil.cpu_percent(interval=1)
    # Mengambil persentase memori RAM yang terpakai
    ram_usage = psutil.virtual_memory().percent
    
    print(f"[ SKILL LOG: CPU: {cpu_usage}% | RAM: {ram_usage}% ]")
    
    # Merakit kalimat agar bisa dibaca oleh mesin TTS
    if cpu_usage > 85:
        return f"Warning, Sir. CPU usage is critically high at {cpu_usage} percent. RAM is at {ram_usage} percent."
    else:
        return f"All systems nominal. CPU is at {cpu_usage} percent, and RAM is at {ram_usage} percent."
