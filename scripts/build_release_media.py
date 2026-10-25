"""Render clearly labelled screenshot-based release media from existing project evidence."""

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
FONT = Path('C:/Windows/Fonts/segoeui.ttf')
BOLD = Path('C:/Windows/Fonts/segoeuib.ttf')
ASSETS = ROOT / 'docs/assets'
FRAME_DIR = ROOT / 'tmp/release-media'
FRAMES = [
    ('reports/message-demo/presentation-photo.png', '01  Фото, OCR и уровень риска', 'Сохранённый авторский синтетический случай'),
    ('reports/message-demo/presentation-mobile-map.png', '02  Маршрут и источники', 'Каждый переход можно открыть для проверки'),
    ('reports/release-2.4/browser/site-ocr.png', '03  Публичный экран OCR', 'Сохранённый пример; новые фото — в локальном приложении'),
    ('reports/release-2.4/browser/site-network.png', '04  Сеть публикаций', 'Структурный тест 5000 сущностей — в отчёте NETWORK_V5'),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD if bold else FONT), size)


def frame(source: Path, title: str, subtitle: str) -> Image.Image:
    canvas = Image.new('RGB', (1280, 720), '#10213d')
    draw = ImageDraw.Draw(canvas)
    draw.text((36, 20), 'SafeTrace KZ  /  SafeNet KZ · Track 2', fill='#90d6eb', font=font(23, True))
    draw.text((36, 61), title, fill='white', font=font(40, True))
    original = Image.open(source).convert('RGB')
    thumb = ImageOps.contain(original, (1220, 550), Image.Resampling.LANCZOS)
    canvas.paste(thumb, ((1280 - thumb.width) // 2, 115 + (550 - thumb.height) // 2))
    draw.text((36, 674), subtitle, fill='#e7eef9', font=font(20))
    return canvas


def social() -> Image.Image:
    canvas = Image.new('RGB', (1280, 640), '#10213d')
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((30, 26, 1250, 614), 25, fill='#193155')
    draw.text((66, 62), 'SAFENET KZ  /  ТРЕК 2', fill='#90d6eb', font=font(27, True))
    draw.text((66, 126), 'SafeTrace KZ', fill='white', font=font(61, True))
    draw.text((66, 213), 'Скрытая игра', fill='#f5bc6d', font=font(48, True))
    draw.text((68, 300), 'Сообщение или фото → OCR → маршрут → источник', fill='white', font=font(24))
    draw.text((68, 360), 'FPR 4,8%   ·   Precision 89,2%   ·   Recall 75,5%', fill='#d6e5fa', font=font(24, True))
    draw.text((68, 406), '640 авторских синтетических случаев · LLM-разметка', fill='#a9c6e5', font=font(21))
    screenshot = Image.open(ROOT / 'reports/message-demo/presentation-photo.png').convert('RGB')
    crop = screenshot.crop((250, 50, 1320, 700))
    crop = ImageOps.contain(crop, (530, 380), Image.Resampling.LANCZOS)
    canvas.paste(crop, (692, 190))
    draw.text((68, 552), 'Проверяемые наблюдения. Решение принимает аналитик.', fill='white', font=font(23))
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    ASSETS.mkdir(parents=True, exist_ok=True)
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    prepared = []
    for index, (path, title, subtitle) in enumerate(FRAMES):
        image = frame(ROOT / path, title, subtitle)
        target = FRAME_DIR / f'demo-frame-{index + 1}.png'
        image.save(target, optimize=True)
        prepared.append(image)
    prepared[0].save(ASSETS / 'interface-tour.gif', save_all=True, append_images=prepared[1:], duration=[4500] * 4, loop=0, optimize=True)
    social().save(ASSETS / 'social-preview-1280x640.png', optimize=True)
    out = ROOT / 'deliverables/releases/SafeTrace-KZ-v3-demo-2min.mp4'
    out.parent.mkdir(parents=True, exist_ok=True)
    concat = ROOT / 'tmp/release-media-frames.txt'
    concat.parent.mkdir(parents=True, exist_ok=True)
    concat.write_text(''.join(f"file '{(FRAME_DIR / f'demo-frame-{i + 1}.png').as_posix()}'\nduration 30\n" for i in range(4)) + f"file '{(FRAME_DIR / 'demo-frame-4.png').as_posix()}'\n", encoding='utf-8')
    subprocess.run([args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(concat), '-t', '120', '-r', '15', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)], check=True)
    print(f'GIF: {ASSETS / "interface-tour.gif"}; social: {ASSETS / "social-preview-1280x640.png"}; video: {out}')


if __name__ == '__main__':
    main()
