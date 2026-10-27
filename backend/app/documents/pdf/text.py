from __future__ import annotations


def is_cjk(char: str) -> bool:
    return ("\u3400" <= char <= "\u9fff") or ("\uf900" <= char <= "\ufaff") or ("\u3000" <= char <= "\u303f")


def flow_text(text: str) -> str:
    """Join PDF visual line breaks into one flowing string."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    result = lines[0]
    for line in lines[1:]:
        if result and is_cjk(result[-1]) and is_cjk(line[0]):
            result += line
        else:
            result += " " + line
    return result
