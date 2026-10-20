"""Render an owned synthetic QR poster for the browser/offline acceptance checks."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
target = root / "reports/core-v2-dev/qr-input.png"
url = "https://go.safetrace.test/r/q7"
matrix = cv2.QRCodeEncoder_create().encode(url)
matrix = cv2.copyMakeBorder(matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
matrix = np.repeat(np.repeat(matrix, 10, axis=0), 10, axis=1)
canvas = Image.new("RGB", (1000, 680), "white")
draw = ImageDraw.Draw(canvas)
font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
draw.text((40, 35), "DEMO. Қосыл да бонус ал!", font=font, fill="#1b2b43")
draw.text((40, 90), "Переходи по QR к предложению.", font=font, fill="#1b2b43")
canvas.paste(Image.fromarray(matrix).convert("RGB"), (40, 165))
draw.text((40, 590), "Авторский синтетический материал SafeTrace.", font=font, fill="#1b2b43")
target.parent.mkdir(parents=True, exist_ok=True)
canvas.save(target)
print(target)
