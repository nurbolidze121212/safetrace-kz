import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
packages = []
for dist in importlib.metadata.distributions():
    meta = dist.metadata
    packages.append(
        {
            "name": meta["Name"],
            "version": dist.version,
            "license": meta.get("License-Expression") or meta.get("License") or "See installed distribution",
            "project_urls": meta.get_all("Project-URL") or [],
        }
    )
lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
node = [
    {
        "name": name.removeprefix("node_modules/"),
        "version": data.get("version"),
        "license": data.get("license", "See distribution"),
        "resolved": data.get("resolved"),
    }
    for name, data in lock["packages"].items()
    if name
]
(ROOT / "reports/dependencies.json").write_text(
    json.dumps(
        {"python": sorted(packages, key=lambda p: p["name"].lower()), "node": node},
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print("Python packages:", len(packages), "Node packages:", len(node))
