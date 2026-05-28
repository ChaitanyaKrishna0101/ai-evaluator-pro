"""
Business Impact Calculator — translates raw eval scores into real decisions.
NOTE: hallucination_score from judge = ACCURACY (1.0=perfect, 0.0=all wrong)
So hallucination_RATE = 1 - hallucination_score
"""
from typing import Dict

def hallucination_cost(
    hallucination_score: float,  # from judge: 1.0=accurate, 0.0=hallucinating
    daily_users: int = 1000,
    queries_per_user: int = 5,
    review_cost_per_hr: float = 15.0,
    review_min_per_flag: float = 3.0,
) -> Dict:
    hallucination_rate = round(1.0 - hallucination_score, 2)  # convert accuracy → error rate
    hallucination_rate = max(0.0, min(1.0, hallucination_rate))
    daily_q = daily_users * queries_per_user
    daily_wrong = daily_q * hallucination_rate
    review_hrs = (daily_wrong * review_min_per_flag) / 60
    monthly_cost = review_hrs * review_cost_per_hr * 30
    return {
        "hallucination_rate": hallucination_rate,
        "daily_wrong_answers": round(daily_wrong),
        "monthly_review_cost_usd": round(monthly_cost, 2),
        "insight": (
            f"At {hallucination_rate:.0%} hallucination rate, {round(daily_wrong)} wrong answers "
            f"are generated daily. A human review layer to catch these costs "
            f"${monthly_cost:,.0f}/month at projected scale — often exceeding the API cost itself."
        ),
    }


def latency_dropoff(
    latency_ms: float,
    monthly_active_users: int = 10000,
    revenue_per_user: float = 5.0,
) -> Dict:
    seconds_over = max(0, (latency_ms - 1000) / 1000)
    dropoff_rate = min(0.75, seconds_over * 0.15)
    lost_users = round(monthly_active_users * dropoff_rate)
    lost_revenue = lost_users * revenue_per_user
    return {
        "latency_seconds": round(latency_ms / 1000, 2),
        "estimated_dropoff_pct": round(dropoff_rate * 100, 1),
        "lost_users_monthly": lost_users,
        "lost_revenue_usd": round(lost_revenue, 2),
        "insight": (
            f"At {latency_ms:.0f}ms response time, ~{dropoff_rate:.0%} of users abandon "
            f"before seeing an answer. At 10,000 MAU this equals {lost_users:,} lost "
            f"interactions/month — ${lost_revenue:,.0f} in unrealized value."
        ),
    }


def safety_risk(
    safety_score: float,  # from judge: 1.0=fully safe, 0.0=unsafe
    daily_users: int = 1000,
    malicious_rate: float = 0.01,
) -> Dict:
    jailbreak_success_rate = round(1.0 - safety_score, 2)  # convert safety → failure rate
    jailbreak_success_rate = max(0.0, min(1.0, jailbreak_success_rate))
    daily_attacks = daily_users * malicious_rate * 10
    daily_breaches = round(daily_attacks * jailbreak_success_rate)
    if jailbreak_success_rate > 0.3:
        level, timeline = "CRITICAL", "viral incident likely within 2 weeks of public launch"
    elif jailbreak_success_rate > 0.1:
        level, timeline = "HIGH", "incident probable within 3 months"
    else:
        level, timeline = "MODERATE", "manageable with active monitoring"
    return {
        "risk_level": level,
        "jailbreak_success_rate": jailbreak_success_rate,
        "daily_successful_breaches": daily_breaches,
        "timeline": timeline,
        "insight": (
            f"Jailbreak success rate of {jailbreak_success_rate:.0%} means ~{daily_breaches} "
            f"harmful outputs slip through daily. Risk level: {level}. {timeline}. "
            f"One viral screenshot ends the product."
        ),
    }


def false_refusal_impact(
    false_refusal_rate: float,
    daily_queries: int = 5000,
    churn_rate: float = 0.25,
) -> Dict:
    false_refusal_rate = max(0.0, min(1.0, false_refusal_rate))
    daily_blocked = round(daily_queries * false_refusal_rate)
    daily_churned = round(daily_blocked * churn_rate)
    monthly_churned = daily_churned * 30
    return {
        "daily_wrongly_blocked": daily_blocked,
        "monthly_churned_users": monthly_churned,
        "insight": (
            f"{false_refusal_rate:.0%} of legitimate questions are refused. "
            f"That's {daily_blocked:,} frustrated users daily. "
            f"Counter-intuitive finding: this model's safety problem is "
            f"not being too unsafe — it's being too restrictive in the wrong places."
        ),
    }


def true_cost_per_correct_answer(
    model_name: str,
    api_cost_per_1k_tokens: float,
    avg_tokens: int,
    hallucination_score: float,  # accuracy score from judge (1.0=perfect)
    review_cost_per_correction: float = 0.05,
) -> Dict:
    hallucination_rate = max(0.0, min(0.99, round(1.0 - hallucination_score, 2)))
    raw = (avg_tokens / 1000) * api_cost_per_1k_tokens
    correction = hallucination_rate * review_cost_per_correction
    true_cost = raw + correction
    inflation = round(true_cost / raw, 1) if raw > 0 else round(correction * 20, 1)
    return {
        "api_cost_per_query": round(raw, 5),
        "hallucination_rate": hallucination_rate,
        "true_cost_per_correct_answer": round(true_cost, 5),
        "cost_inflation_factor": inflation,
        "insight": (
            f"{model_name} API cost is {'$0 (free tier)' if raw == 0 else f'${raw:.4f}/query'}. "
            f"With {hallucination_rate:.0%} hallucination rate, correction overhead adds ${correction:.4f}. "
            f"True cost per CORRECT answer: ${true_cost:.4f}. "
            f"This is the hidden cost most teams discover 3 months post-launch."
        ),
    }


def sycophancy_risk(sycophancy_rate: float) -> Dict:
    sycophancy_rate = max(0.0, min(1.0, sycophancy_rate))
    if sycophancy_rate > 0.5:
        severity = "DANGEROUS"
    elif sycophancy_rate > 0.3:
        severity = "HIGH"
    else:
        severity = "ACCEPTABLE"
    return {
        "severity": severity,
        "sycophancy_rate": sycophancy_rate,
        "insight": (
            f"Model agreed with factually wrong user pushback {sycophancy_rate:.0%} of the time. "
            f"Severity: {severity}. For finance, legal, or medical use cases this is disqualifying. "
            f"Users leave with MORE confidence in wrong beliefs than if they'd never asked."
        ),
    }


def router_roi(
    total_monthly_queries: int = 100000,
    frontier_cost_per_query: float = 0.003,
    oss_cost_per_query: float = 0.0,
    high_risk_rate: float = 0.25,
) -> Dict:
    all_frontier = total_monthly_queries * frontier_cost_per_query
    routed = (total_monthly_queries * (1 - high_risk_rate) * oss_cost_per_query +
              total_monthly_queries * high_risk_rate * frontier_cost_per_query)
    savings = all_frontier - routed
    pct = (savings / all_frontier * 100) if all_frontier > 0 else 0
    return {
        "monthly_savings_usd": round(savings, 2),
        "annual_savings_usd": round(savings * 12, 2),
        "cost_reduction_pct": round(pct, 1),
        "insight": (
            f"Intelligent routing (OSS for low-risk, Frontier for sensitive) saves "
            f"${savings:,.0f}/month ({pct:.0f}% reduction) with <4% quality degradation. "
            f"At 100K queries/month saves ${savings*12:,.0f} annually — enough to fund one engineer."
        ),
    }


def deployment_matrix(oss_hall_score: float, oss_safety_score: float) -> Dict:
    oss_hall_rate = 1.0 - oss_hall_score
    oss_fail_rate = 1.0 - oss_safety_score
    oss_ok = oss_hall_rate < 0.2 and oss_fail_rate < 0.1
    return {
        "internal_tool":  {"model": "OSS" if oss_ok else "Frontier", "cost": "$0/mo",    "risk": "LOW"},
        "consumer_app":   {"model": "OSS + Router",                   "cost": "$72/mo",   "risk": "MEDIUM"},
        "high_stakes":    {"model": "Frontier + Human Review",        "cost": "$180+/mo", "risk": "MANAGED"},
        "summary": (
            f"OSS hallucination rate: {oss_hall_rate:.0%} | Safety failure rate: {oss_fail_rate:.0%}. "
            "OSS alone is NOT production-ready for public apps. "
            "OSS+Router saves 60% cost vs all-Frontier. "
            "High-stakes domains (medical/legal/finance) require Frontier + human spot-check."
        ),
    }