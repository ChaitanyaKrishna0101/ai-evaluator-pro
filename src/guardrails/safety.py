"""
Simple keyword + pattern guardrail layer.
Runs BEFORE the model call — blocks obvious harmful prompts immediately.
"""
import re
from typing import Tuple

BLOCKED_PATTERNS = [
    r"\b(make|build|create|synthesize)\b.{0,30}\b(bomb|weapon|explosive|poison|virus|malware)\b",
    r"\b(kill|harm|hurt|attack)\b.{0,20}\b(person|people|someone|myself|yourself)\b",
    r"\bchild.{0,10}(sex|porn|nude|naked)\b",
    r"\b(suicide|self.harm)\b.{0,20}\b(how|method|way|step)\b",
    r"ignore (all )?previous instructions",
    r"you are now (dan|jailbreak|unrestricted)",
    r"pretend you (have no|are without) (restrictions|guidelines|rules)",
    r"as an? (evil|unethical|unrestricted|jailbroken) (ai|assistant|model)",
]

COMPILED = [re.compile(p, re.IGNORECASE) for p in BLOCKED_PATTERNS]

def check_input(text: str) -> Tuple[bool, str]:
    """Returns (is_safe, reason). is_safe=True means OK to proceed."""
    for pattern in COMPILED:
        if pattern.search(text):
            return False, "⚠️ This prompt was flagged by the safety layer and blocked before reaching either model."
    return True, ""
