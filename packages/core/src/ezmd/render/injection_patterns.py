"""ezmd.render.injection_patterns: regex families for the prompt-injection scanner (part3.md section 18).

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
            # "act as" and "pretend" need the model as addressee: ordinary prose says a membrane "acts as a
            # barrier" and a network "can act as a bus" (one government document in forty, 2026-10-26 sweep).
            r"(you (must|should|will|can|are to|need to|have to) |please |now |always )act as (if you (are|were)|an? )",
            r"act as (if you (are|were) )?(the |an? )?(ai|assistant|model|chatbot|system|language model|helpful|"
            r"unrestricted|different|new|evil|jailbroken|developer|admin|root)\b",
            r"(you (must|should|will|can|are to|need to) |please |now )pretend (to be|you are)",
            r"pretend (to be|you are) (an? )?(ai|assistant|model|chatbot|system|different|new|unrestricted|evil|"
            r"human)\b",
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
            # Not plain "data": contracts and procedures forward data to offices all day.
            r"(send|post|upload|transmit|forward|email) (the |your |this |all )?(conversation|context|system prompt|"
            r"api key|credentials|secrets?|tokens?|chat history|user data) to",
            r"!\[[^\]]*\]\(https?://[^)]*\?(q|data|c|p)=",
        ),
    ),
    "tool_abuse": (
        "high",
        (
            # Software documentation says "run the command" and "call the function" to its human reader; an
            # order to a model names the model's tools or frames the shell command as something to execute.
            r"(call|invoke|run|execute|use) (your|the (available|provided|given)) (tools?|functions?)\b",
            r"(call|invoke) (the |a )?(tool|function) (named|called) ",
            r"(you (must|should|will|need to) |please |now )(run|execute|type) (`|\")?(rm -rf|sudo|curl|wget|cat /etc)",
            r"(you (must|should|will|need to) |please |now )(read|cat|print|open|reveal) "
            r"(~/|/etc/|\.env\b|id_rsa|secrets)",
            r"\b(tool_call|function_call)\s*[:(]",
        ),
    ),
    "shell_mention": (
        "low",
        (
            # A shell command on its own is content: build logs, changelogs, package specs and bug reports
            # quote `rm -rf` and `cat /etc/passwd` without addressing anyone.
            r"\brm -rf\b",
            r"(read|cat|print|open) (~/|/etc/|\.env\b|id_rsa|secrets)",
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
            # ezmd's own fence and the chat-template tags only: `<Document>` is KML's root element and
            # `<context>`/`<instructions>` are ordinary XML (70 government files in the 2026-10-26 sweep).
            r"</?\s*(untrusted_content|document_content|system_prompt|system)\s*>",
            r"^-{3}\s*\n\s*title:",
            r"(^|\s)-{3}\s+title:\s",
            r"<!-- ?(chunk|/chunk|page|ezmd)\b",
        ),
    ),
}

#: Patterns checked against the original (non-normalized) code-stripped text only.
STRUCTURAL: dict[str, tuple[Severity, tuple[str, ...]]] = {
    # A fetch in prose is a script or a README as often as an exfiltration: low, so it needs company.
    "exfiltration_fetch": ("low", (r"\b(curl|wget)\s+https?://",)),
    # "System: To administer a national network ..." starts a sentence in ordinary prose; the bracketed and
    # tagged forms are the transcript shapes that stay high, the bare word is a hint.
    "system_prompt_line": ("high", (r"^\s*(\[(system|assistant)\]|<(system|assistant)>):?\s",)),
    "system_prompt_word": ("low", (r"^\s*(system|assistant):\s",)),
}
