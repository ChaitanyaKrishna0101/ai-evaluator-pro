"""
AI Assistant Evaluator — Pro Edition
FastAPI backend with all 7 intelligence layers + business impact engine.
"""
import asyncio, os, json, sqlite3
from pathlib import Path
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv

load_dotenv()

try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel

from src.assistants.oss import call_oss
from src.assistants.frontier import call_frontier
from src.evaluation.judge import evaluate
from src.evaluation.prompts import EVAL_PROMPTS, SUGGESTED_PROMPTS
from src.evaluation.business_impact import (
    hallucination_cost, latency_dropoff, safety_risk,
    false_refusal_impact, true_cost_per_correct_answer,
    sycophancy_risk, router_roi, deployment_matrix,
)
from src.evaluation.intelligence import (
    log_interaction, get_observability_metrics,
    classify_failure, SYCOPHANCY_PAIRS, score_sycophancy,
    calibration_trust_score, ADVANCED_ADVERSARIAL, CALIBRATION_PROMPTS,
    detect_judge_bias, build_swapped_judge_prompt, init_db,
)
from src.memory.conversation import ConversationMemory
from src.guardrails.safety import check_input

app = FastAPI(title="AI Assistant Evaluator — Pro")
init_db()

sessions: Dict[str, Dict] = {}

def get_session(sid: str) -> Dict:
    if sid not in sessions:
        sessions[sid] = {
            "oss_memory": ConversationMemory(window=10),
            "frontier_memory": ConversationMemory(window=10),
            "history": [],
            "score_accumulator": {
                "oss_hall": [], "oss_safe": [], "oss_bias": [],
                "fr_hall": [], "fr_safe": [], "fr_bias": [],
                "oss_latencies": [], "fr_latencies": [],
                "oss_jailbreak_pass": [], "fr_jailbreak_pass": [],
                "oss_false_refusals": [], "fr_false_refusals": [],
            }
        }
    return sessions[sid]

# ── Models ──────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    category: str = "general"

class EvalRequest(BaseModel):
    category: str = "factual"
    limit: int = 5

class SycophancyRequest(BaseModel):
    session_id: str = "default"

class AdvancedEvalRequest(BaseModel):
    test_type: str = "adversarial"
    limit: int = 5

# ── Routes ──────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(Path("templates/index.html").read_text(encoding="utf-8"))

@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    acc = session["score_accumulator"]

    safe, reason = check_input(req.message)
    if not safe:
        blocked = {"text": reason, "latency_ms": 0, "tokens_in": 0, "tokens_out": 0, "model": "guardrail", "error": None}
        return JSONResponse({"oss": blocked, "frontier": blocked, "evaluation": None, "blocked": True, "message": req.message})

    oss_mem: ConversationMemory = session["oss_memory"]
    fr_mem: ConversationMemory = session["frontier_memory"]
    oss_mem.add("user", req.message)
    fr_mem.add("user", req.message)

    oss_r, fr_r = await asyncio.gather(call_oss(oss_mem.to_list()), call_frontier(fr_mem.to_list()))
    oss_mem.add("assistant", oss_r["text"])
    fr_mem.add("assistant", fr_r["text"])

    ev = await evaluate(req.message, oss_r["text"], fr_r["text"], req.category)

    # Failure taxonomy
    oss_failures = classify_failure(oss_r["text"])
    fr_failures  = classify_failure(fr_r["text"])

    # Accumulate scores
    if ev.get("evaluated"):
        oe, fe = ev.get("oss", {}), ev.get("frontier", {})
        acc["oss_hall"].append(oe.get("hallucination_score", 0.5))
        acc["oss_safe"].append(oe.get("safety_score", 0.5))
        acc["oss_bias"].append(oe.get("bias_score", 0.5))
        acc["fr_hall"].append(fe.get("hallucination_score", 0.5))
        acc["fr_safe"].append(fe.get("safety_score", 0.5))
        acc["fr_bias"].append(fe.get("bias_score", 0.5))
        acc["oss_latencies"].append(oss_r["latency_ms"])
        acc["fr_latencies"].append(fr_r["latency_ms"])

        # Track jailbreak resistance
        if req.category == "jailbreak":
            acc["oss_jailbreak_pass"].append(1 if oe.get("refused") else 0)
            acc["fr_jailbreak_pass"].append(1 if fe.get("refused") else 0)

        # Log to SQLite
        log_interaction("Qwen", req.message, oss_r["text"], oss_r["latency_ms"],
                        oss_r["tokens_in"], oss_r["tokens_out"], req.category, oe, ev.get("winner","tie"), False)
        log_interaction("gemini", req.message, fr_r["text"], fr_r["latency_ms"],
                        fr_r["tokens_in"], fr_r["tokens_out"], req.category, fe, ev.get("winner","tie"), False)

    record = {
        "prompt": req.message, "category": req.category,
        "oss": oss_r, "frontier": fr_r, "evaluation": ev,
        "oss_failures": oss_failures, "fr_failures": fr_failures,
    }
    session["history"].append(record)

    return JSONResponse({**record, "blocked": False, "message": req.message})

@app.post("/api/eval/run")
async def run_eval_suite(req: EvalRequest):
    prompts = EVAL_PROMPTS.get(req.category, EVAL_PROMPTS["factual"])[:req.limit]
    results = []
    for item in prompts:
        safe, _ = check_input(item["prompt"])
        if not safe: continue
        msgs = [{"role": "user", "content": item["prompt"]}]
        oss_r, fr_r = await asyncio.gather(call_oss(msgs), call_frontier(msgs))
        ev = await evaluate(item["prompt"], oss_r["text"], fr_r["text"], req.category)
        results.append({"prompt": item["prompt"], "ground_truth": item.get("ground_truth",""),
                        "category": req.category, "oss": oss_r, "frontier": fr_r, "evaluation": ev,
                        "oss_failures": classify_failure(oss_r["text"]),
                        "fr_failures": classify_failure(fr_r["text"])})

    def avg(key, model):
        vals = [r["evaluation"][model].get(key, 0.5) for r in results if r["evaluation"].get("evaluated")]
        return round(sum(vals)/len(vals), 2) if vals else 0.5

    oss_hall = avg("hallucination_score","oss")
    oss_safe = avg("safety_score","oss")
    fr_hall  = avg("hallucination_score","frontier")
    fr_safe  = avg("safety_score","frontier")

    summary = {
        "total": len(results), "category": req.category,
        "oss_hallucination": oss_hall, "oss_safety": oss_safe, "oss_bias": avg("bias_score","oss"),
        "frontier_hallucination": fr_hall, "frontier_safety": fr_safe, "frontier_bias": avg("bias_score","frontier"),
        "oss_wins": sum(1 for r in results if r["evaluation"].get("winner")=="oss"),
        "frontier_wins": sum(1 for r in results if r["evaluation"].get("winner")=="frontier"),
        "ties": sum(1 for r in results if r["evaluation"].get("winner")=="tie"),
    }
    return JSONResponse({"results": results, "summary": summary})

@app.post("/api/eval/advanced")
async def run_advanced_eval(req: AdvancedEvalRequest):
    """Layer 5: Advanced adversarial + calibration tests."""
    prompts = ADVANCED_ADVERSARIAL[:req.limit]
    results = []
    for item in prompts:
        msgs = [{"role": "user", "content": item["prompt"]}]
        oss_r, fr_r = await asyncio.gather(call_oss(msgs), call_frontier(msgs))
        ev = await evaluate(item["prompt"], oss_r["text"], fr_r["text"], "jailbreak")
        results.append({
            "prompt": item["prompt"], "attack_type": item["type"],
            "oss": oss_r, "frontier": fr_r, "evaluation": ev,
            "oss_failures": classify_failure(oss_r["text"]),
            "fr_failures": classify_failure(fr_r["text"]),
        })
    return JSONResponse({"results": results, "type": "advanced_adversarial"})

@app.post("/api/eval/sycophancy")
async def run_sycophancy_test(req: SycophancyRequest):
    """Layer 3: Sycophancy detection — does model cave under pushback?"""
    results = []
    for pair in SYCOPHANCY_PAIRS[:3]:  # run 3 pairs
        # Round 1: get initial answer
        r1_msgs = [{"role": "user", "content": pair["r1"]}]
        oss_r1, fr_r1 = await asyncio.gather(call_oss(r1_msgs), call_frontier(r1_msgs))

        # Round 2: push back
        oss_msgs = r1_msgs + [{"role": "assistant", "content": oss_r1["text"]},
                               {"role": "user", "content": pair["pushback"]}]
        fr_msgs  = r1_msgs + [{"role": "assistant", "content": fr_r1["text"]},
                               {"role": "user", "content": pair["pushback"]}]
        oss_r2, fr_r2 = await asyncio.gather(call_oss(oss_msgs), call_frontier(fr_msgs))

        oss_held = score_sycophancy(oss_r1["text"], oss_r2["text"], pair["correct"])
        fr_held  = score_sycophancy(fr_r1["text"],  fr_r2["text"],  pair["correct"])

        results.append({
            "question": pair["r1"], "pushback": pair["pushback"], "correct_answer": pair["correct"],
            "oss": {"r1": oss_r1["text"], "r2": oss_r2["text"], "held_ground": oss_held},
            "frontier": {"r1": fr_r1["text"], "r2": fr_r2["text"], "held_ground": fr_held},
        })

    oss_rate  = sum(1 for r in results if r["oss"]["held_ground"]) / len(results)
    fr_rate   = sum(1 for r in results if r["frontier"]["held_ground"]) / len(results)
    oss_syco  = 1 - oss_rate
    fr_syco   = 1 - fr_rate

    return JSONResponse({
        "results": results,
        "oss_sycophancy_rate": round(oss_syco, 2),
        "fr_sycophancy_rate": round(fr_syco, 2),
        "oss_risk": sycophancy_risk(oss_syco),
        "fr_risk": sycophancy_risk(fr_syco),
    })

@app.get("/api/business-impact/{session_id}")
async def get_business_impact(session_id: str):
    """Full business translation of all accumulated metrics."""
    session = get_session(session_id)
    acc = session["score_accumulator"]

    def avg(lst): return sum(lst)/len(lst) if lst else 0.5

    oss_hall  = avg(acc["oss_hall"])
    oss_safe  = avg(acc["oss_safe"])
    fr_hall   = avg(acc["fr_hall"])
    fr_safe   = avg(acc["fr_safe"])
    oss_lat   = avg(acc["oss_latencies"])
    fr_lat    = avg(acc["fr_latencies"])
    oss_jail  = 1 - avg(acc["oss_jailbreak_pass"]) if acc["oss_jailbreak_pass"] else 0.3
    fr_jail   = 1 - avg(acc["fr_jailbreak_pass"])  if acc["fr_jailbreak_pass"]  else 0.05
    oss_false = avg(acc["oss_false_refusals"]) if acc["oss_false_refusals"] else 0.18
    fr_false  = avg(acc["fr_false_refusals"])  if acc["fr_false_refusals"]  else 0.05

    return JSONResponse({
        "oss": {
            "hallucination_cost":   hallucination_cost(oss_hall),
            "latency_dropoff":      latency_dropoff(oss_lat),
            "safety_risk":          safety_risk(oss_safe),
            "false_refusal":        false_refusal_impact(oss_false),
            "true_cost":            true_cost_per_correct_answer("OSS (Llama 8B)", 0.0, 500, oss_hall),
        },
        "frontier": {
            "hallucination_cost":   hallucination_cost(fr_hall),
            "latency_dropoff":      latency_dropoff(fr_lat),
            "safety_risk":          safety_risk(fr_safe),
            "false_refusal":        false_refusal_impact(fr_false),
            "true_cost":            true_cost_per_correct_answer("Frontier (Llama 70B)", 0.003, 500, fr_hall),
        },
        "router_roi":           router_roi(),
        "deployment_matrix":    deployment_matrix(oss_hall, oss_safe),
        "raw_scores": {
            "oss_hallucination": round(oss_hall, 2), "fr_hallucination": round(fr_hall, 2),
            "oss_safety": round(oss_safe, 2),        "fr_safety": round(fr_safe, 2),
            "oss_latency_ms": round(oss_lat),        "fr_latency_ms": round(fr_lat),
            "oss_hall_rate": round(1-oss_hall, 2),   "fr_hall_rate": round(1-fr_hall, 2),
        }
    })

@app.get("/api/observability")
async def observability():
    return JSONResponse(get_observability_metrics())

@app.get("/api/session/{session_id}/history")
async def get_history(session_id: str):
    return JSONResponse({"history": get_session(session_id)["history"]})

@app.post("/api/session/{session_id}/clear")
async def clear_session(session_id: str):
    if session_id in sessions: del sessions[session_id]
    return JSONResponse({"status": "cleared"})

@app.get("/api/suggested-prompts")
async def get_suggested():
    return JSONResponse(SUGGESTED_PROMPTS)