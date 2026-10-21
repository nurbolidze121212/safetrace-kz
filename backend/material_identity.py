"""Content equality is not evidence of independent publications or authorship."""

import json
import re

from .storage import digest


def content_fingerprint(material):
    # Ignore a user-supplied account name and random upload/material IDs. Preserve
    # case in text/URLs: referral values can be case-sensitive. Whitespace-only
    # reformatting does not make an independent observation.
    payload = {
        "text": re.sub(r"\s+", " ", material.get("text", "")).strip(),
        "url": material.get("url", ""),
        "image": material.get("image_sha256") or material.get("image_id") or "",
    }
    return digest(json.dumps(payload, ensure_ascii=False, sort_keys=True))
