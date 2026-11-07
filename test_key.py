import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

print("Pinging Google servers. Active models for this key:")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
