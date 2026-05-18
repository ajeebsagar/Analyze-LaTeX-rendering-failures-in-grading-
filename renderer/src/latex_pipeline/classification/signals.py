"""Signal detectors. Each detector adheres to ISignalDetector (LSP).

Adding a new signal type = adding a new class. The classifier composes
detectors; it doesn't know their internals (OCP).
"""
from __future__ import annotations

import re
from typing import List

from ..core import ISignalDetector


# ---- Shared regex vocabulary ----
MATH_COMMANDS = frozenset({
    # ===== Greek lowercase =====
    "alpha","beta","gamma","delta","epsilon","varepsilon","zeta","eta",
    "theta","vartheta","iota","kappa","varkappa","lambda","mu","nu","xi",
    "omicron","pi","varpi","rho","varrho","sigma","varsigma","tau","upsilon",
    "phi","varphi","chi","psi","omega",
    # ===== Greek uppercase =====
    "Alpha","Beta","Gamma","Delta","Epsilon","Zeta","Eta","Theta","Iota",
    "Kappa","Lambda","Mu","Nu","Xi","Omicron","Pi","Rho","Sigma","Tau",
    "Upsilon","Phi","Chi","Psi","Omega",
    # ===== Fractions / roots / binomials =====
    "frac","tfrac","dfrac","cfrac","binom","tbinom","dbinom",
    "sqrt","root",
    # ===== Big operators =====
    "sum","prod","int","iint","iiint","oint","coprod",
    "bigcap","bigcup","bigvee","bigwedge","bigsqcup","bigotimes","bigoplus",
    "bigodot","biguplus",
    # ===== Operators / functions =====
    "lim","liminf","limsup","sup","inf","min","max",
    "log","ln","exp",
    "sin","cos","tan","cot","sec","csc",
    "arcsin","arccos","arctan",
    "sinh","cosh","tanh","coth",
    "arg","deg","det","dim","gcd","hom","ker",
    "mod","bmod","pmod","pod",
    "Pr","operatorname",
    # ===== Comparison / relation =====
    "le","leq","leqq","leqslant","ge","geq","geqq","geqslant",
    "ne","neq","approx","approxeq","equiv","cong","simeq","sim",
    "propto","asymp","doteq",
    "gg","ll","ggg","lll",
    "prec","preceq","succ","succeq",
    "vdash","dashv","models","perp","parallel",
    # ===== Set membership =====
    "in","ni","notin","subset","subseteq","supset","supseteq",
    "subsetneq","supsetneq","cap","cup","setminus","emptyset","varnothing",
    # ===== Arrows =====
    "to","mapsto","longmapsto","gets",
    "rightarrow","leftarrow","leftrightarrow",
    "Rightarrow","Leftarrow","Leftrightarrow",
    "longrightarrow","longleftarrow","longleftrightarrow",
    "Longrightarrow","Longleftarrow","Longleftrightarrow",
    "implies","iff","impliedby",
    "uparrow","downarrow","Uparrow","Downarrow",
    "hookrightarrow","hookleftarrow","twoheadrightarrow","twoheadleftarrow",
    "rightleftharpoons","leftrightharpoons",
    "xrightarrow","xleftarrow","xrightleftharpoons",
    # ===== Binary operators =====
    "cdot","times","div","pm","mp","ast","star",
    "oplus","ominus","otimes","oslash","odot",
    "wedge","vee","land","lor","neg","lnot",
    "circ","bullet","cdotp","ldotp",
    # ===== Letter-like symbols =====
    "infty","aleph","beth","gimel","daleth","ell","hbar","wp",
    "Re","Im","imath","jmath","mho",
    "forall","exists","nexists","top","bot","partial","nabla",
    "complement","triangle","square","Box","diamondsuit",
    # ===== Math fonts =====
    "mathrm","mathbf","mathbb","mathcal","mathit","mathsf","mathtt",
    "mathfrak","mathscr","mathnormal",
    "bm","boldsymbol",
    "text","textbf","textit","textrm","textsf","texttt","textnormal",
    # ===== Sizing / delimiters =====
    "left","right","middle",
    "big","Big","bigg","Bigg",
    "bigl","Bigl","biggl","Biggl","bigr","Bigr","biggr","Biggr",
    "bigm","Bigm","biggm","Biggm",
    "langle","rangle","lvert","rvert","lVert","rVert",
    "lceil","rceil","lfloor","rfloor","lbrace","rbrace",
    # ===== Accents / decorations =====
    "hat","widehat","tilde","widetilde","bar","overline","underline",
    "vec","overrightarrow","overleftarrow","overleftrightarrow",
    "dot","ddot","dddot","ddddot",
    "acute","grave","check","breve","mathring",
    "overbrace","underbrace","stackrel","overset","underset",
    # ===== Environments =====
    "begin","end",
    "matrix","pmatrix","bmatrix","Bmatrix","vmatrix","Vmatrix",
    "smallmatrix","cases","array","aligned","alignedat","gathered","split",
    "subarray",
    # ===== Spacing / structural =====
    "limits","nolimits","substack","cancel","bcancel","not",
    # ===== Punctuation / misc math =====
    "colon","ldots","cdots","vdots","ddots","dots","dotsb","dotsc","dotsi","dotsm","dotso",
    "prime","backprime","circ","degree","therefore","because",
    "atop","over","choose",
    # ===== Symbols for sets =====
    "mathbb",  # kept above; also \R, \N, \Z, \Q via mathbb
    # ===== Boxed / highlighted =====
    "boxed","fbox",
})

_RE_COMMAND = re.compile(r"\\([a-zA-Z]+)")
_RE_SUPER = re.compile(r"[A-Za-z0-9}\)\]]\^[A-Za-z0-9{(\-]")
_RE_SUB = re.compile(r"[A-Za-z0-9}\)\]]_[A-Za-z0-9{(\-]")
_RE_OP = re.compile(r"[+\-*/=<>^_]")
_RE_DIGIT = re.compile(r"\d")
_RE_HTML = re.compile(r"<(table|tr|td|th|p|strong|br|thead|tbody|div|span)\b", re.I)
_RE_FILL_BLANK = re.compile(r"_{3,}")
_RE_CURRENCY = re.compile(r"^\s*\d+(?:[,.]\d+)*\s*(?:[A-Za-z]{1,15}(?:\s+[A-Za-z]{1,15}){0,3})?\s*$")
_RE_PURE_ALPHA = re.compile(r"^[A-Za-z]{1,15}$")
_RE_ETA = re.compile(r"(?<![\\A-Za-z])eta\b")
_RE_RAC = re.compile(r"(?<![A-Za-z])rac\{")
_RE_EXT = re.compile(r"(?<![\\A-Za-z])ext\{")
_RE_ALPHAETA = re.compile(r"alphaeta\b")


# ----------------------------------------------------------------------
# Detectors

class HtmlSignal(ISignalDetector):
    @property
    def name(self) -> str: return "html"
    def detect(self, content, *, inside_math_delim):
        if _RE_HTML.search(content):
            return {"flags": {"is_html": True}, "signals": {"html": True}}
        return {}


class FillBlankSignal(ISignalDetector):
    @property
    def name(self) -> str: return "fill_blank"
    def detect(self, content, *, inside_math_delim):
        if not inside_math_delim and _RE_FILL_BLANK.search(content):
            return {"flags": {"is_fill_blank": True}, "signals": {"fill_blank": True}}
        return {}


class CurrencySignal(ISignalDetector):
    @property
    def name(self) -> str: return "currency"
    def detect(self, content, *, inside_math_delim):
        if not inside_math_delim and _RE_CURRENCY.match(content):
            return {"flags": {"is_currency": True}, "signals": {"currency": True}, "score": -0.6}
        return {}


class CommandSignal(ISignalDetector):
    @property
    def name(self) -> str: return "command"
    def detect(self, content, *, inside_math_delim):
        known = [m.group(1) for m in _RE_COMMAND.finditer(content) if m.group(1) in MATH_COMMANDS]
        if not known:
            return {}
        return {"score": min(0.35, 0.12 * len(known)),
                "signals": {"known_commands": len(known)}}


class SubSuperSignal(ISignalDetector):
    @property
    def name(self) -> str: return "sub_super"
    def detect(self, content, *, inside_math_delim):
        n_super = len(_RE_SUPER.findall(content))
        n_sub = len(_RE_SUB.findall(content))
        if not (n_super or n_sub):
            return {}
        return {"score": min(0.15, 0.05 * (n_super + n_sub)),
                "signals": {"super": n_super, "sub": n_sub}}


class OperatorDensitySignal(ISignalDetector):
    @property
    def name(self) -> str: return "operator_density"
    def detect(self, content, *, inside_math_delim):
        n_op = len(_RE_OP.findall(content))
        n_digit = len(_RE_DIGIT.findall(content))
        sig = {}
        score = 0.0
        if n_op: sig["operators"] = n_op
        if n_digit: sig["digits"] = n_digit
        if n_op >= 2 and n_digit >= 1:
            score = 0.1
        return {"score": score, "signals": sig} if (score or sig) else {}


class PureAlphaSignal(ISignalDetector):
    """Pure-alpha short token outside math delim looks like a stray word."""
    @property
    def name(self) -> str: return "pure_alpha"
    def detect(self, content, *, inside_math_delim):
        if not inside_math_delim and _RE_PURE_ALPHA.match(content.strip()):
            return {"score": -0.4, "signals": {"pure_alpha_token": True}}
        return {}


class CorruptionSignal(ISignalDetector):
    """Detects orphan-backslash corruption (eta, rac, ext, alphaeta)."""
    @property
    def name(self) -> str: return "corruption"
    def detect(self, content, *, inside_math_delim):
        hits = []
        if _RE_ETA.search(content): hits.append("eta")
        if _RE_RAC.search(content): hits.append("rac")
        if _RE_EXT.search(content): hits.append("ext")
        if _RE_ALPHAETA.search(content): hits.append("alphaeta")
        if not hits:
            return {}
        # Boost score slightly so repair pipeline runs.
        return {"score": 0.15, "flags": {"has_corruption": True},
                "signals": {"corruption": hits}}


def default_signal_detectors() -> List[ISignalDetector]:
    """The default detector pack. Override in the builder to customize."""
    return [
        HtmlSignal(),
        FillBlankSignal(),
        CurrencySignal(),
        CommandSignal(),
        SubSuperSignal(),
        OperatorDensitySignal(),
        PureAlphaSignal(),
        CorruptionSignal(),
    ]
