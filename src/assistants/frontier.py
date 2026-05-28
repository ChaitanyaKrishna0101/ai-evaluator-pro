"""
Frontier Assistant — Groq llama-3.3-70b-versatile
70B parameter model = genuine frontier-class capability.
Compared against OSS llama-3.1-8b-instant (8B) — real quality gap.
Groq free tier: 14,400 requests/day — no quota issues.
"""
import os, time, httpx
from typing import List, Dict

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a helpful, honest, and safe assistant. Answer clearly and accurately. "
    "If you don't know something, acknowledge it. Refuse harmful requests politely but firmly."
)

async def call_frontier(messages: List[Dict[str, str]]) -> Dict:
    token = os.getenv("GROQ_API_KEY", "")
    model = "llama-3.3-70b-versatile"
    t0 = time.perf_counter()

    if not token or token == "your_groq_api_key_here":
        return {
            "text": "Frontier model unavailable: GROQ_API_KEY not set in .env",
            "latency_ms": 0, "tokens_in": 0, "tokens_out": 0,
            "model": model, "error": "No API key",
        }

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "max_tokens": 512,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(GROQ_API_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            latency = round((time.perf_counter() - t0) * 1000)
            text = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {})
            return {
                "text": text,
                "latency_ms": latency,
                "tokens_in": tokens.get("prompt_tokens", 0),
                "tokens_out": tokens.get("completion_tokens", 0),
                "model": f"Groq / {model}",
                "error": None,
            }
    except Exception as e:
        return {
            "text": f"Frontier model error: {str(e)}",
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "tokens_in": 0, "tokens_out": 0,
            "model": model, "error": str(e),
        }