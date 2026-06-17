"""Mechanical answer extraction from model output. No model calls, no judgement."""
import re


def extract_boxed(text: str) -> str | None:
    """Return the content of the LAST \\boxed{...}, brace-balanced."""
    if not text:
        return None
    idx = text.rfind(r"\boxed{")
    if idx == -1:
        return None
    i = idx + len(r"\boxed{")
    depth = 1
    out = []
    while i < len(text) and depth:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        out.append(c)
        i += 1
    return "".join(out).strip()


def extract_int(text: str) -> int | None:
    """AIME-style integer answer (0-999). Prefer \\boxed{}, else last integer."""
    b = extract_boxed(text)
    src = b if b is not None else (text or "")
    nums = re.findall(r"-?\d+", src.replace(",", ""))
    if not nums:
        return None
    try:
        return int(nums[-1])
    except ValueError:
        return None


def extract_mc_letter(text: str, n_options: int = 4) -> str | None:
    """Multiple-choice letter (A.. ). Prefer \\boxed{}, then 'answer is X', then last lone letter."""
    letters = "".join(chr(ord("A") + i) for i in range(n_options))
    b = extract_boxed(text)
    if b:
        m = re.search(rf"[{letters}]", b.upper())
        if m:
            return m.group(0)
    if text:
        m = re.search(rf"answer\s*(?:is|:)?\s*\(?([{letters}])\)?", text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        m = re.findall(rf"(?<![A-Za-z])([{letters}])(?![A-Za-z])", text.upper())
        if m:
            return m[-1]
    return None


def extract_code(text: str, lang: str = "python") -> str | None:
    """Last fenced code block; prefer the requested language, else any fence, else raw."""
    if not text:
        return None
    blocks = re.findall(rf"```{lang}\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not blocks:
        blocks = re.findall(r"```[a-zA-Z0-9]*\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    return text.strip()
