"""Download pinned official CPU model assets once; runtime never auto-downloads."""

import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("PP-OCRv5_mobile_det", "cyrillic_PP-OCRv5_mobile_rec")
BASE = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/"


def main():
    (ROOT / "models").mkdir(exist_ok=True)
    for name in NAMES:
        target = ROOT / "models" / name
        if not (target / "inference.json").is_file():
            cache = Path.home() / ".paddlex" / "official_models" / name
            if (cache / "inference.json").is_file():
                shutil.copytree(cache, target, dirs_exist_ok=True)
            else:
                print("Downloading official model:", name, flush=True)
                with tempfile.TemporaryDirectory(prefix="safetrace-model-") as folder:
                    archive = Path(folder) / "model.tar"
                    with urllib.request.urlopen(BASE + name + "_infer.tar", timeout=90) as response:
                        with archive.open("wb") as output:
                            shutil.copyfileobj(response, output)
                    extracted = Path(folder) / "extracted"
                    with tarfile.open(archive) as tar:
                        tar.extractall(extracted, filter="data")
                    model = next(extracted.rglob("inference.json")).parent
                    shutil.copytree(model, target, dirs_exist_ok=True)
    files = {}
    for name in NAMES:
        for path in sorted((ROOT / "models" / name).rglob("*")):
            if path.is_file() and not any(x.startswith(".") for x in path.relative_to(ROOT / "models").parts):
                files[str(path.relative_to(ROOT / "models")).replace("\\", "/")] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    expected_path = ROOT / "models-manifest.json"
    if expected_path.exists():
        expected = json.loads(expected_path.read_text(encoding="utf-8"))["files"]
        if files != expected:
            raise RuntimeError(
                "Model hashes differ from models-manifest.json. Do not silently replace the model."
            )
    else:
        expected_path.write_text(
            json.dumps({"models": list(NAMES), "source": BASE, "files": files}, indent=2), encoding="utf-8"
        )
    print("Models ready; hashes verified.")


if __name__ == "__main__":
    main()
