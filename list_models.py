import requests
from config import OLLAMA_BASE_URL

print(f"Using Ollama Host: {OLLAMA_BASE_URL}")

try:
    print("Listing available Ollama models...")
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
        data = response.json()
        models = data.get("models", [])
        if not models:
            print("No models installed on this Ollama instance.")
        for model in models:
            name = model.get("name")
            details = model.get("details", {})
            parameter_size = details.get("parameter_size", "unknown")
            quantization_level = details.get("quantization_level", "unknown")
            print(f"Model Name: {name} | Size: {parameter_size} | Quantization: {quantization_level}")
    else:
        print(f"Error: Ollama returned status code {response.status_code}: {response.text}")
except Exception as e:
    print(f"Error connecting to Ollama: {e}")
