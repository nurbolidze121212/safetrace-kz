"""Extract exactly the spoken pitch paragraphs for a local synthetic voice timing."""

import argparse
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--version", choices=["v3"], default="v3")
args = parser.parse_args()
source = root / "docs/PITCH.md"
pitch = source.read_text(encoding="utf-8").split("## 0:00", 1)[1].split("## Тезисы", 1)[0]
text = "\n".join(line for line in pitch.splitlines()[1:] if not line.startswith("## ")).strip()
text = text.replace(chr(96), "")
folder = root / "data/rehearsal" / args.version
folder.mkdir(parents=True, exist_ok=True)
(folder / "pitch.txt").write_text(text, encoding="utf-8", newline="\n")
(root / f"reports/acceptance-{args.version}/pitch-text.json").write_text(
    json.dumps(
        {
            "words": len(re.findall(r"\S+", text)),
            "source": "docs/PITCH.md",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": text,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
    newline="\n",
)
print(len(re.findall(r"\S+", text)), "words")
