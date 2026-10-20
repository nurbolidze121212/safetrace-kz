import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATA = Path(os.getenv("SAFETRACE_DATA_DIR") or ROOT / "data").resolve()
MODEL_DIR = ROOT / "models"
RULE_VERSION = "rules-3.0-dev"
OCR_VERSION = "cyrillic_PP-OCRv5_mobile_rec+PP-OCRv5_mobile_det|layout-rotation-2.0"
QR_VERSION = "qr-1.0"
PIPELINE_VERSION = "pipeline-2.1"
MAX_IMAGE = 8 * 1024 * 1024
MAX_TEXT = 20000
MAX_MATERIALS = 20
MAX_REQUESTS = 12
MAX_BODY = 256 * 1024
MAX_DEPTH = 4


def allowed_hosts() -> set[str]:
    return {x.strip().lower() for x in os.getenv("SAFETRACE_ALLOWED_HOSTS", "").split(",") if x.strip()}


def offline() -> bool:
    return os.getenv("SAFETRACE_OFFLINE", "0") == "1"
