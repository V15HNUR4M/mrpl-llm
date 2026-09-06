import re
from typing import Any, Dict, List, Union

SENSITIVE_KEY_PATTERNS = [
    re.compile(r"pass(word)?", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"auth(orization)?", re.IGNORECASE),
    re.compile(r"jwt", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"cookie", re.IGNORECASE),
    re.compile(r"private[_-]?key", re.IGNORECASE),
    re.compile(r"credit[_-]?card", re.IGNORECASE),
]

DISALLOWED_RAW_KEYS = {
    "prompt",
    "prompt_text",
    "system_prompt",
    "response",
    "response_text",
    "model_response",
    "raw_bytes",
    "images",
    "image_data",
    "base64",
    "b64_data",
    "file_content",
}

def is_sensitive_key(key: str) -> bool:
    key_str = str(key).strip().lower()
    if key_str in DISALLOWED_RAW_KEYS:
        return True
    return any(pattern.search(key_str) for pattern in SENSITIVE_KEY_PATTERNS)

def sanitize_metadata(obj: Any, max_depth: int = 5) -> Any:
    if max_depth <= 0:
        return "[MAX_DEPTH_REACHED]"

    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            k_str = str(k)
            k_lower = k_str.lower()
            
            # 1. Prompt / Response text non-persistence: replace with length / metadata
            if k_lower in ("prompt", "prompt_text", "system_prompt"):
                if isinstance(v, str):
                    cleaned[f"{k_str}_length"] = len(v)
                    cleaned[k_str] = "[PROMPT_OMITTED]"
                else:
                    cleaned[k_str] = "[PROMPT_OMITTED]"
            elif k_lower in ("response", "response_text", "model_response"):
                if isinstance(v, str):
                    cleaned[f"{k_str}_length"] = len(v)
                    cleaned[k_str] = "[RESPONSE_OMITTED]"
                else:
                    cleaned[k_str] = "[RESPONSE_OMITTED]"
            # 2. Binary / Image / Base64 data: never log
            elif k_lower in ("images", "image_data", "base64", "b64_data", "raw_bytes", "file_content"):
                cleaned[k_str] = "[BINARY_OMITTED]"
            # 3. Passwords, Tokens, Secrets, API keys
            elif is_sensitive_key(k_str):
                if isinstance(v, (dict, list, tuple, set)):
                    cleaned[k_str] = sanitize_metadata(v, max_depth=max_depth - 1)
                else:
                    cleaned[k_str] = "[REDACTED]"
            else:
                cleaned[k_str] = sanitize_metadata(v, max_depth=max_depth - 1)
        return cleaned

    elif isinstance(obj, (list, tuple, set)):
        return [sanitize_metadata(item, max_depth=max_depth - 1) for item in obj]

    elif isinstance(obj, (bytes, bytearray)):
        return f"[BINARY_DATA_{len(obj)}_BYTES]"

    elif isinstance(obj, str):
        # Truncate strings that are suspiciously huge (> 4KB) or look like base64 blobs
        if len(obj) > 4096:
            return obj[:128] + f"... [TRUNCATED_{len(obj)}_CHARS]"
        if len(obj) > 200 and obj.startswith("data:image/"):
            return "[BASE64_IMAGE_OMITTED]"
        return obj

    return obj
