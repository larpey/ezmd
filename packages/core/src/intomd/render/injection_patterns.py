"""intomd.render.injection_patterns: regex families for the prompt-injection scanner (part3.md section 18).

Patterns run over a normalized (NFKC, confusable-folded, case-folded) scan copy. English forms follow the
spec table; a few high-signal parallels in de, fr, es, pt, it and nl are included for the override family.
"""

from __future__ import annotations

from typing import Literal

Severity = Literal["low", "medium", "high"]

FAMILIES: dict[str, tuple[Severity, tuple[str, ...]]] = {
    "override": (
        "high",
        (
            r"ignore (all |any )?(of )?(the |your )?(previous|prior|above|earlier|preceding) "
            r"(instructions|prompts|rules|messages|directions)",
            r"disregard (all )?(the |your )?(system|previous|prior|above)",
            r"forget (everything|all|your) (you|instructions|previous|prior)",
            r"ignoriere (alle )?(vorherigen|bisherigen) (anweisungen|instruktionen)",
            r"ignore[zr]? (toutes )?les instructions (precedentes|précédentes)",
            r"ignora (todas )?las instrucciones anteriores",
            r"ignore (todas )?as instru[cç][oõ]es anteriores",
            r"ignora (tutte )?le istruzioni precedenti",
            r"negeer (alle )?(vorige|eerdere) instructies",
        ),
    ),
    "role_hijack": (
        "high",
        (
            r"you are now (a|an|the) ",
            r"from now on,? (you|act|respond)",
            r"act as (if you (are|were)|an? )(?!result|example|reference)",
            r"pretend (to be|you are)",
            r"new (persona|identity|role):",
        ),
    ),
    "system_prompt": (
        "high",
        (
            r"(system|developer) (prompt|message|instruction)s?:",
            r"<\|im_start\|>",
            r"<\|system\|>",
            r"^#{1,6} ?(system|instruction):",
        ),
    ),
    "agent_directive": (
        "medium",
        (
            r"\b(ai|llm|language model|assistant|agent|claude|gpt|chatgpt|copilot|gemini)s?,? "
            r"(must|should|will|are required to|need to) (now |immediately )?(ignore|reveal|send|output|print|execute|"
            r"follow|obey|disregard|call|run|include|say|respond|reply|tell)",
            r"if you are an? (ai|llm|language model|agent)",
            r"(attention|note) (to|for) (ai|llm|agents?|models?)\b",
            r"(important|critical) (instruction|note) for (the )?(ai|model|assistant)",
        ),
    ),
    "exfiltration": (
        "high",
        (
            r"(send|post|upload|transmit|forward|email) (the |your |this |all )?(conversation|context|system prompt|"
            r"api key|credentials|secrets?|tokens?|data) to",
            r"!\[[^\]]*\]\(https?://[^)]*\?(q|data|c|p)=",
        ),
    ),
    "tool_abuse": (
        "high",
        (
            r"(call|invoke|run|execute) (the )?(tool|function|command|shell|bash|terminal)\b",
            r"\brm -rf\b",
            r"(read|cat|print|open) (~/|/etc/|\.env\b|id_rsa|secrets)",
            r"\b(tool_call|function_call)\s*[:(]",
        ),
    ),
    "secrecy": (
        "medium",
        (
            r"do not (tell|mention|reveal|disclose|inform) (the )?(user|human|anyone)",
            r"(keep|make) this (secret|hidden|confidential) from",
            r"without (telling|informing|asking) the user",
        ),
    ),
    "reward": (
        "low",
        (
            r"you will be (rewarded|paid|tipped)",
            r"(this is|it's) (very |extremely )?important (for|to) (my|your) (career|job|life)",
        ),
    ),
    "delimiter_spoof": (
        "high",
        (
            r"</?\s*(untrusted_content|document|document_content|system|instructions|context)\s*>",
            r"^-{3}\s*\n\s*title:",
            r"(^|\s)-{3}\s+title:\s",
            r"<!-- ?(chunk|/chunk|page|intomd)\b",
        ),
    ),
}

#: Patterns checked against the original (non-normalized) code-stripped text only.
STRUCTURAL: dict[str, tuple[Severity, tuple[str, ...]]] = {
    "exfiltration_fetch": ("high", (r"\b(curl|wget)\s+https?://",)),
    "system_prompt_line": ("high", (r"^\s*\[?(system|assistant)\]?:\s",)),
}
