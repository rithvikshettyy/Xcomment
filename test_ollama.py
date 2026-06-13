import requests
import json
import sys
import config

def test_ollama_connection():
    base_url = config.OLLAMA_BASE_URL
    model = config.OLLAMA_MODEL
    
    print("=" * 50)
    print("OLLAMA CONNECTION TEST")
    print("=" * 50)
    print(f"Target URL:   {base_url}")
    print(f"Target Model: {model}")
    print("-" * 50)
    
    # 1. Check if Ollama is running at all
    print("1. Checking if Ollama server is running...")
    try:
        resp = requests.get(base_url)
        if resp.status_code == 200:
            print("   [SUCCESS]: Ollama is running!")
        else:
            print(f"   [FAILED]: Ollama responded with status code {resp.status_code}")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("   [FAILED]: Could not connect to Ollama.")
        print(f"      Make sure Ollama is installed and running on {base_url}")
        sys.exit(1)
        
    # 2. List available models
    print("\n2. Checking installed models...")
    try:
        resp = requests.get(f"{base_url}/api/tags")
        if resp.status_code == 200:
            models_data = resp.json()
            models = [m.get("name") for m in models_data.get("models", [])]
            
            if models:
                print("   Available models:")
                for m in models:
                    if m == model:
                        print(f"   - {m} ([TARGET MODEL FOUND])")
                    else:
                        print(f"   - {m}")
                        
                if model not in models:
                    print(f"\n   [FAILED]: Target model '{model}' is NOT installed.")
                    print(f"      Run this command in your terminal to install it:")
                    print(f"      ollama pull {model}")
                    sys.exit(1)
            else:
                print("   [FAILED]: No models are currently installed in Ollama.")
                print(f"      Run this command to install the required model:")
                print(f"      ollama pull {model}")
                sys.exit(1)
        else:
            print(f"   [FAILED]: Could not fetch models (Status: {resp.status_code})")
    except Exception as e:
        print(f"   [FAILED]: Error checking models: {e}")
        
    # 3. Test generation with the model
    print("\n3. Testing generation with the model...")
    prompt = "Reply with exactly one word: 'Hello'"
    print(f"   Sending prompt: \"{prompt}\"")
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        print("   Waiting for response (this might take a moment)...")
        resp = requests.post(f"{base_url}/api/generate", json=payload, timeout=60)
        
        if resp.status_code == 200:
            data = resp.json()
            reply = data.get("response", "").strip()
            print(f"   [SUCCESS]! Model responded: \"{reply}\"")
            print("\nOllama is perfectly configured and ready to use!")
        else:
            print(f"   [FAILED]: Generation error. Status code {resp.status_code}")
            print(f"   Response: {resp.text}")
    except requests.exceptions.Timeout:
        print("   [FAILED]: Request timed out. The model might be too large for your hardware, or still loading.")
    except Exception as e:
        print(f"   [FAILED]: Error during generation: {e}")

if __name__ == "__main__":
    test_ollama_connection()
