import requests
from config import OLLAMA_HOST, OLLAMA_MODEL

def call_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
            timeout=120
        )
        resp.raise_for_status()
        return (resp.json().get("response") or "").strip()
    except Exception as e:
        return f"[OLLAMA_ERROR] {e}"
