"""Copied existing helper functions without project-relative input side effects."""
def check_response(case, answer):
    missing = [group for group in case["required"] if not any(word in answer for word in group)]
    forbidden = [word for word in case["forbidden"] if word in answer]
    return {"cue_pass": bool(answer.strip()) and not missing and not forbidden,
            "missing_cues": missing, "forbidden_phrases": forbidden}
