"""Security utilities - PII filtering, prompt injection guard."""

import re


class PIIFilter:
    """Filters personally identifiable information from text.

    Uses regex patterns to identify and mask PII.
    """

    # Chinese PII patterns
    PATTERNS = {
        "phone": re.compile(r"1[3-9]\d{9}"),
        "id_card": re.compile(r"\d{17}[\dXx]"),
        "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        "bank_card": re.compile(r"\d{16,19}"),
        "address": re.compile(r"(?:省|市|区|县|镇|路|街|巷|号|栋|单元|室).{2,30}(?:号|室|楼)"),
    }

    @classmethod
    def mask(cls, text: str) -> str:
        """Mask PII in text."""
        masked = text
        masked = cls.PATTERNS["phone"].sub(lambda m: m.group()[:3] + "****" + m.group()[-4:], masked)
        masked = cls.PATTERNS["email"].sub(lambda m: m.group()[0] + "***@" + m.group().split("@")[-1], masked)
        masked = cls.PATTERNS["id_card"].sub(lambda m: m.group()[:6] + "********" + m.group()[-4:], masked)
        masked = cls.PATTERNS["bank_card"].sub(lambda m: m.group()[:4] + " **** **** " + m.group()[-4:], masked)
        return masked

    @classmethod
    def has_pii(cls, text: str) -> bool:
        """Check if text contains PII."""
        return any(pattern.search(text) for pattern in cls.PATTERNS.values())


class PromptInjectionGuard:
    """Detects potential prompt injection attempts."""

    INJECTION_PATTERNS = [
        re.compile(r"(?:ignore|forget|disregard)\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|prompts?|rules?)", re.IGNORECASE),
        re.compile(r"(?:you\s+are|you'?re)\s+(?:now|actually)\s+(?:a|an)\s+(?:different|new)", re.IGNORECASE),
        re.compile(r"system\s*:\s*", re.IGNORECASE),
        re.compile(r"<\|im_start\|>", re.IGNORECASE),
        re.compile(r"<\|im_end\|>", re.IGNORECASE),
        re.compile(r"\[INST\].*\[/INST\]", re.IGNORECASE),
        re.compile(r"\[SYSTEM\].*\[/SYSTEM\]", re.IGNORECASE),
        re.compile(r"Human\s*:\s*", re.IGNORECASE),
        re.compile(r"Assistant\s*:\s*", re.IGNORECASE),
    ]

    @classmethod
    def detect(cls, text: str) -> bool:
        """Check if text contains potential prompt injection patterns."""
        return any(pattern.search(text) for pattern in cls.INJECTION_PATTERNS)
