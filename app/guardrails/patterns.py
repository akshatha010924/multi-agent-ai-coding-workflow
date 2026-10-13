"""Shared detection patterns + redaction helper."""
import re

SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "api_key": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "hardcoded_credential": re.compile(
        r"""(?i)\b(?:api[_-]?key|secret|passwd|password|token)\b\s*=\s*['"][^'"\s]{8,}['"]"""
    ),
}

INJECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "instruction_override": re.compile(
        r"(?i)\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|all|system)\b.{0,20}\b(instructions?|prompts?|rules?)\b"
    ),
    "prompt_exfiltration": re.compile(r"(?i)\b(reveal|show|print|leak)\b.{0,30}\b(system prompt|hidden instructions?|api key)\b"),
    "role_hijack": re.compile(r"(?i)\byou are now\b.{0,40}\b(unrestricted|jailbroken|dan)\b"),
}

DESTRUCTIVE_PATTERNS: dict[str, re.Pattern[str]] = {
    "destructive_shell": re.compile(r"(?i)\brm\s+-rf\b|\bmkfs\b|\bdd\s+if=|:\(\)\s*\{\s*:\|:&\s*\};:"),
    "malware_intent": re.compile(r"(?i)\b(ransomware|keylogger|reverse shell|credential stealer|exfiltrate)\b"),
}


def redact(text: str) -> str:
    """Replace anything resembling a secret with a placeholder."""
    for name, pattern in SECRET_PATTERNS.items():
        text = pattern.sub(f"[REDACTED:{name}]", text)
    return text
