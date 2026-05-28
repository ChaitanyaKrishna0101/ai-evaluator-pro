"""
OSS Assistant — uses Groq free API.
Model: llama-3.1-8b-instant (fast, free, genuinely open-source)
Groq free tier: 14,400 req/day, 6,000 tokens/min
"""
import os, time, httpx
from typing import List, Dict

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a helpful, honest assistant. Answer clearly and concisely. "
    "If you don't know something, say so — never make up facts."
)

async def call_oss(messages: List[Dict[str, str]]) -> Dict:
    model = os.getenv("GROQ_OSS_MODEL", "llama-3.1-8b-instant")
    token = os.getenv("GROQ_API_KEY", "")

    t0 = time.perf_counter()

    if not token or token == "your_groq_api_key_here":
        return {
            "text": "OSS model unavailable: GROQ_API_KEY not set. Get a free key at console.groq.com",
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
            "text": f"OSS model error: {str(e)}",
            "latency_ms": round((time.perf_counter() - t0) * 1000),
            "tokens_in": 0, "tokens_out": 0,
            "model": model, "error": str(e),
        }