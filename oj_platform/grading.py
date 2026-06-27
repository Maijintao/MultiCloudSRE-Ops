import json
import re


def iter_json_object_candidates(text):
    if not text:
        return
    for start_match in re.finditer(r"\{", text):
        start = start_match.start()
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield text[start : index + 1]
                    break


def extract_json_object(text):
    if not text:
        return None
    candidates = []
    for fenced in re.finditer(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.I):
        candidates.extend(iter_json_object_candidates(fenced.group(1).strip()))
    candidates.extend(iter_json_object_candidates(text))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def normalize_score(value):
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            value = match.group(0)
    try:
        score = int(round(float(value)))
        return max(0, min(100, score))
    except Exception:
        return None


def extract_score_from_text(text):
    if not text:
        return None
    patterns = (
        r'"score"\s*:\s*"?(\d+(?:\.\d+)?)(?:\s*/\s*100)?"?',
        r"(?:score|total|grade|points|总分|得分|评分|分数)\D{0,20}(\d{1,3}(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            score = normalize_score(match.group(1))
            if score is not None:
                return score
    return None


def verdict_for_score(score):
    score = normalize_score(score)
    if score is None:
        return None
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "pass"
    return "fail"


def has_meaningful_agent_output(text):
    compact = (text or "").strip()
    if not compact:
        return False
    return compact.lower() not in {"(empty)", "empty", "none", "null"}
