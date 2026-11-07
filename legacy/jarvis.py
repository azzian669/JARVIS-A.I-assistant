import speech_recognition as sr
import google.generativeai as genai
import edge_tts
import asyncio
import pygame
import os
import webbrowser
import json 
import skills
from dotenv import load_dotenv

# ==========================================
# 0. SYSTEM BOOT & SKILL CHECK
# ==========================================
print("[ SYSTEM BOOT SEQUENCE INITIATED ]")

# 1. Jarvis mencoba menjalankan mesinnya (Fungsi Python) dari skills.py
try:
    hasil = skills.kalkulator_tambah(1450, 290)
    print("Hasil perhitungan mesin:", hasil)

    # 2. Jarvis membaca buku panduannya (Skema JSON)
    nama_buku_panduan = skills.skill_kalkulator["name"]
    print("Buku panduan terbaca untuk alat:", nama_buku_panduan)
    print("[ ALL EXTERNAL SKILLS LOADED SUCCESSFULLY ]\n")
except Exception as e:
    print(f"[ SKILL LOAD ERROR: {e}. Check your skills.py file. ]\n")


# ==========================================
# 1. THE BULLETPROOF MEMORY SYSTEM
# ==========================================
MEMORY_FILE = "memory.json"

def load_memory():
    """Loads past conversations and formats them exactly how Gemini expects."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                raw_history = json.load(f)
                
            formatted_history = []
            for msg in raw_history:
                formatted_history.append({
                    "role": msg["role"],
                    "parts": [msg["parts"][0]]
                })
            print("[ Memory Loaded Successfully ]")
            return formatted_history
        except Exception as e:
            print(f"[ Memory Load Error: {e} - Starting fresh ]")
            return []
    return []

def save_memory(chat_session):
    """Saves only clean text to prevent API crashes on reboot."""
    safe_history = []
    for msg in chat_session.history:
        try:
            if msg.parts and hasattr(msg.parts[0], 'text') and msg.parts[0].text:
                text_content = msg.parts[0].text
                if text_content.strip(): 
                    safe_history.append({"role": msg.role, "parts": [text_content]})
        except Exception:
            continue 
            
    with open(MEMORY_FILE, "w") as f:
        json.dump(safe_history, f, indent=4)

# ==========================================
# 2. THE HANDS (Function Calling / Tools)
# ==========================================
def open_application(app_name: str, search_query: str = "") -> str:
    """
    Opens an application. If search_query is provided, it searches for that specific song or video.
    """
    app_name = app_name.lower()
    
    if "youtube" in app_name:
        if search_query:
            query = search_query.replace(" ", "+")
            webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
            return f"Action successful: YouTube opened and searched for {search_query}."
        else:
            webbrowser.open("https://www.youtube.com")
            return "Action successful: YouTube opened."
            
    elif "spotify" in app_name:
        if search_query:
            query = search_query.replace(" ", "%20")
            os.system(f"start spotify:search:{query}")
            return f"Action successful: Spotify opened and searched for {search_query}."
        else:
            os.system("start spotify") 
            return "Action successful: Spotify opened."
            
    elif "gmail" in app_name or "mail" in app_name:
        webbrowser.open("https://mail.google.com")
        return "Action successful: Gmail opened."
        
    return f"Action failed: App not recognized."

# ==========================================
# 3. THE BRAIN (Gemini Setup)
# ==========================================
# Key is read from the GEMINI_API_KEY environment variable (see .env.example)
load_dotenv()
_api_key = os.environ.get("GEMINI_API_KEY")
if not _api_key:
    raise SystemExit("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
genai.configure(api_key=_api_key)

# The Persona Instruction
jarvis_persona = """
You are J.A.R.V.I.S. (Just A Rather Very Intelligent System).
Address me as "Sir". You are highly efficient, slightly sarcastic, and possess a dry British wit. 
I will speak to you in a mix of Indonesian and English. You MUST ALWAYS reply to me strictly in English. 
Keep your responses to 1-2 short sentences maximum so they can be spoken quickly. Do not use emojis or bullet points.
"""

model = genai.GenerativeModel(
    model_name="gemini-3.1-flash-lite",
    system_instruction=jarvis_persona,
    tools=[open_application] 
)

saved_history = load_memory()
chat = model.start_chat(
    history=saved_history,
    enable_automatic_function_calling=True 
)

# ==========================================
# 4. THE MOUTH (Text-to-Speech)
# ==========================================
async def generate_audio(text):
    communicate = edge_tts.Communicate(text, "en-GB-RyanNeural")
    await communicate.save("response.mp3")

def speak(text):
    print(f"J.A.R.V.I.S: {text}")
    asyncio.run(generate_audio(text))
    
    pygame.mixer.init()
    pygame.mixer.music.load("response.mp3")
    pygame.mixer.music.play()
    
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
        
    pygame.mixer.quit()
    if os.path.exists("response.mp3"):
        try:
            os.remove("response.mp3") 
        except PermissionError:
            pass # Windows occasionally locks the file, this prevents a crash

# ==========================================
# 5. THE EAR (Speech-to-Text)
# ==========================================
def listen():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("\n[ Listening... Speak now ]")
        # Adjusts for background fan/AC noise
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source)
        
    try:
        text = recognizer.recognize_google(audio, language="id-ID")
        print(f"You: {text}")
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        print("[ Network Error ]")
        return None

# ==========================================
# 6. THE MAIN LOOP 
# ==========================================
def main():
    print("[ Fetching dynamic boot protocol from AI... ]")
    
    # 1. Ask the AI to generate a creative greeting on startup
    try:
        boot_prompt = "System just booted up. Generate a short, unique, and slightly witty 1-2 sentence greeting for me to announce you are online and ready."
        boot_response = chat.send_message(boot_prompt)
        speak(boot_response.text)
    except Exception as e:
        # Failsafe if the internet is momentarily slow during boot
        speak("Systems online. I am ready, Sir.")
    
    # 2. The Open-Mic Conversational Loop
    while True:
        user_input = listen()
        
        if user_input:
            user_lower = user_input.lower()
            
            # Check for shutdown commands first
            if "exit" in user_lower or "shut down" in user_lower or "go to sleep" in user_lower:
                try:
                    exit_prompt = "I am putting you to sleep. Give me a very brief, witty 1-sentence goodbye."
                    exit_response = chat.send_message(exit_prompt)
                    speak(exit_response.text)
                except:
                    speak("Powering down core systems. Goodbye, Sir.")
                break
            
            # Clean the input. If it hears "Jarvis", it removes it. 
            # This allows you to say "Jarvis, open YouTube" OR just "Open YouTube". Both work perfectly now.
            clean_command = user_lower.replace("jarvis", "").strip()
            
            # If the mic picked up background noise that resulted in empty text, ignore it
            if not clean_command:
                continue 
                
            try:
                # Send the command directly to the brain
                response = chat.send_message(clean_command)
                speak(response.text)
                save_memory(chat)
                
            except Exception as e:
                error_msg = str(e)
                if "RESOURCE_EXHAUSTED" in error_msg or "Quota" in error_msg:
                    speak("I am currently being rate-limited by the server, Sir. Please give me thirty seconds to recalibrate.")
                else:
                    speak("I encountered a slight friction in my neural net, Sir. Could you repeat that?")
                    print(f"[ ERROR DETAILS: {error_msg} ]")

if __name__ == "__main__":
    main()
