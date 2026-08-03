import re

from app.models.enums import WritingTaskType

WORD_RANGE_PATTERN = re.compile(r"150\s*[–-]\s*200", re.IGNORECASE)
BULLET_POINT_PATTERN = re.compile(r"(?m)^\s*•\s+\S")
PERSONAL_NAME_PATTERN = re.compile(
    r",\s*(?:(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?[A-Z][a-z]+"
    r"(?:\s+[A-Z][a-z]+)?(?=,|\s+to\b)"
)
DATE_TIME_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:include|give|provide|mention|state|specify|identify)\b"
    r"[^.\n•]{0,40}\b(?:date|dates|time|times)\b",
    re.IGNORECASE,
)
COACHING_PATTERN = re.compile(
    r"\b(?:be|remain)\s+(?:clear|specific|reasonable|concise)\b"
    r"|\b(?:clear|specific)\s+and\s+(?:reasonable|concise)\b"
    r"|\bkeep\b[^.\n]{0,60}\b(?:clear|specific|reasonable|concise)\b",
    re.IGNORECASE,
)


def task_style_issues(task_type: WritingTaskType, prompt: str) -> list[str]:
    normalized = prompt.replace("â€“", "–")
    lowered = normalized.casefold()
    issues: list[str] = []

    if not WORD_RANGE_PATTERN.search(normalized):
        issues.append("Include the 150–200 word instruction.")
    if any(character in normalized for character in "()[]{}"):
        issues.append("Do not include brackets, parentheses, or parenthetical hints.")
    if COACHING_PATTERN.search(normalized):
        issues.append(
            "Do not coach the candidate to be clear, specific, reasonable, or concise."
        )
    if DATE_TIME_REQUIREMENT_PATTERN.search(normalized):
        issues.append("Do not require the candidate to provide dates or times.")

    if task_type == WritingTaskType.EMAIL:
        if "write an email to" not in lowered:
            issues.append("Task 1 must clearly identify the email recipient.")
        elif not re.search(
            r"(?i)\bwrite an email to (?:your|the|a|an)\b", normalized
        ):
            issues.append("Task 1 must use a generic recipient role, not a personal name.")
        if PERSONAL_NAME_PATTERN.search(normalized):
            issues.append("Task 1 must not include an invented personal name.")
        if not re.search(r"use an? [^\n.]{2,30} tone\.", lowered):
            issues.append("Task 1 must specify the required tone.")
        if "address all three points below" not in lowered:
            issues.append("Task 1 must introduce exactly three required points.")
        if len(BULLET_POINT_PATTERN.findall(normalized)) != 3:
            issues.append("Task 1 must contain exactly three bullet points marked with •.")
    else:
        question_type_markers = (
            "choose one option",
            "choose the better option",
            "agree or disagree",
            "which is more important",
            "make a recommendation",
            "recommend one option",
            "which do you think is better",
            "state your opinion",
        )
        if not any(marker in lowered for marker in question_type_markers):
            issues.append("Task 2 must ask for a clear choice, opinion, or recommendation.")
        if "support your" not in lowered or "reason" not in lowered:
            issues.append("Task 2 must request supporting reasons.")
        if "example" not in lowered:
            issues.append("Task 2 must request supporting examples.")

    return issues
