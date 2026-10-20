"""Extract exactly the spoken pitch paragraphs for a local synthetic voice timing."""

import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pitch = (root / "docs/PITCH.md").read_text(encoding="utf-8").split("## 0:00", 1)[1].split("## Тезисы", 1)[0]
text = "\n".join(line for line in pitch.splitlines()[1:] if not line.startswith("## ")).strip()
text = text.replace(chr(96), "")
folder = root / "data/rehearsal"
folder.mkdir(parents=True, exist_ok=True)
(folder / "pitch.txt").write_text(text, encoding="utf-8")
(root / "reports/acceptance-v2/pitch-text.json").write_text(
    json.dumps(
        {"words": len(re.findall(r"\S+", text)), "source": "docs/PITCH.md", "text": text},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(len(re.findall(r"\S+", text)), "words")
