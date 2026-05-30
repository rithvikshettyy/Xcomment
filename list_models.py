import google.generativeai as genai
from config import GEMINI_API_KEY

print(f"Using API Key: {GEMINI_API_KEY[:8]}...{GEMINI_API_KEY[-4:] if len(GEMINI_API_KEY) > 8 else ''}")
genai.configure(api_key=GEMINI_API_KEY)

try:
    print("Listing available models...")
    for model in genai.list_models():
        print(f"Model Name: {model.name} | Supported Methods: {model.supported_generation_methods}")
except Exception as e:
    print(f"Error: {e}")
