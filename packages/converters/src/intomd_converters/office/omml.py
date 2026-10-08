"""A small OMML (Office Math) to LaTeX walker (Part 2 2c step 12).

Covers the common subset: runs, fractions, super/subscripts, radicals, n-ary operators (sums, integrals,
products), delimiters, matrices, functions, accents, bars, lower/upper limits, and equation arrays. Anything
else falls back to its plain text and marks the result partial so the caller can warn `equation_partial`.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree  # type: ignore[import-untyped]

from intomd_converters.office._ooxml_ns import M, local, ns_of, q

_SYMBOLS: dict[str, str] = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon", "ζ": r"\zeta",
    "η": r"\eta", "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu",
    "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\phi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega", "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta",
    "Λ": r"\Lambda", "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
    "±": r"\pm", "×": r"\times", "÷": r"\div", "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "∞": r"\infty", "→": r"\to", "⋅": r"\cdot", "∂": r"\partial", "∇": r"\nabla", "∈": r"\in",
    "∑": r"\sum", "∫": r"\int", "∏": r"\prod", "∮": r"\oint", "√": r"\sqrt{}",
}  # fmt: skip
_NARY = {"∑": r"\sum", "∫": r"\int", "∏": r"\prod", "∮": r"\oint", "∬": r"\iint", "∭": r"\iiint", "⋃": r"\bigcup"}
_ACCENTS = {"̂": r"\hat", "̃": r"\tilde", "̄": r"\bar", "⃗": r"\vec", "̇": r"\dot", "̈": r"\ddot"}
_FUNCS = ("sin", "cos", "tan", "log", "ln", "exp", "lim", "max", "min", "sec", "csc", "cot", "det")


@dataclass(slots=True)
class MathResult:
    latex: str
    text: str
    partial: bool


class _Walker:
    def __init__(self) -> None:
        self.partial = False

    def kids(self, el: etree._Element | None) -> str:
        if el is None:
            return ""
        return "".join(self.node(c) for c in el)

    def arg(self, el: etree._Element, name: str) -> str:
        return self.kids(el.find(q(M, name)))

    def chr_of(self, el: etree._Element, pr: str, default: str) -> str:
        c = el.find(f"{q(M, pr)}/{q(M, 'chr')}")
        if c is None:
            return default
        return str(c.get(q(M, "val")) or default)

    def node(self, el: etree._Element) -> str:
        if ns_of(el.tag) != M:
            return ""
        name = local(el.tag)
        if name == "r":
            return "".join(_latex_text(t.text or "") for t in el.iter(q(M, "t")))
        if name in ("e", "num", "den", "sup", "sub", "deg", "fName", "lim", "oMath"):
            return self.kids(el)
        if name == "f":
            return r"\frac{" + self.arg(el, "num") + "}{" + self.arg(el, "den") + "}"
        if name == "sSup":
            return "{" + self.arg(el, "e") + "}^{" + self.arg(el, "sup") + "}"
        if name == "sSub":
            return "{" + self.arg(el, "e") + "}_{" + self.arg(el, "sub") + "}"
        if name == "sSubSup":
            return "{" + self.arg(el, "e") + "}_{" + self.arg(el, "sub") + "}^{" + self.arg(el, "sup") + "}"
        if name == "rad":
            deg = self.arg(el, "deg")
            return (r"\sqrt[" + deg + "]{" if deg else r"\sqrt{") + self.arg(el, "e") + "}"
        if name == "nary":
            op = _NARY.get(self.chr_of(el, "naryPr", "∫"), r"\int")
            sub, sup = self.arg(el, "sub"), self.arg(el, "sup")
            return op + ("_{" + sub + "}" if sub else "") + ("^{" + sup + "}" if sup else "") + " " + self.arg(el, "e")
        if name == "d":
            end_el = el.find(f"{q(M, 'dPr')}/{q(M, 'endChr')}")
            end = str(end_el.get(q(M, "val")) or "") if end_el is not None else ")"
            beg_el = el.find(f"{q(M, 'dPr')}/{q(M, 'begChr')}")
            beg = str(beg_el.get(q(M, "val")) or "") if beg_el is not None else "("
            inner = ",".join(self.kids(e) for e in el.findall(q(M, "e")))
            return r"\left" + _delim(beg) + inner + r"\right" + _delim(end)
        if name == "m":
            rows = [" & ".join(self.kids(e) for e in mr.findall(q(M, "e"))) for mr in el.findall(q(M, "mr"))]
            return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
        if name == "func":
            fname = self.arg(el, "fName").strip()
            head = "\\" + fname if fname in _FUNCS else r"\operatorname{" + fname + "}"
            return head + " " + self.arg(el, "e")
        if name == "acc":
            acc = _ACCENTS.get(self.chr_of(el, "accPr", "̂"), r"\hat")
            return acc + "{" + self.arg(el, "e") + "}"
        if name == "bar":
            return r"\overline{" + self.arg(el, "e") + "}"
        if name == "limLow":
            return "{" + self.arg(el, "e") + "}_{" + self.arg(el, "lim") + "}"
        if name == "limUpp":
            return "{" + self.arg(el, "e") + "}^{" + self.arg(el, "lim") + "}"
        if name == "eqArr":
            return r"\begin{aligned}" + r" \\ ".join(self.kids(e) for e in el.findall(q(M, "e"))) + r"\end{aligned}"
        if name.endswith("Pr") or name in ("ctrlPr", "argPr"):
            return ""
        self.partial = True
        return "".join(_latex_text(t) for t in el.itertext())


def _delim(ch: str) -> str:
    return {"{": r"\{", "}": r"\}", "|": "|", "‖": r"\|", "⟨": r"\langle", "⟩": r"\rangle", "": "."}.get(ch, ch)


def _latex_text(s: str) -> str:
    return "".join(_SYMBOLS.get(ch, ch) + (" " if ch in _SYMBOLS and _SYMBOLS[ch][-1].isalpha() else "") for ch in s)


def omml_to_latex(el: etree._Element) -> MathResult:
    """Convert an `m:oMath` or `m:oMathPara` element."""
    w = _Walker()
    maths = [el] if local(el.tag) == "oMath" else list(el.iter(q(M, "oMath")))
    latex = r" \\ ".join(w.kids(m).strip() for m in maths)
    text = "".join("".join(t.text or "" for t in m.iter(q(M, "t"))) for m in maths)
    return MathResult(latex=" ".join(latex.split()), text=text, partial=w.partial)
