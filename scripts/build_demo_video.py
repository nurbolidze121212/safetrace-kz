"""Create a clearly labelled 120-second overview from actual browser screenshots."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENES = [
    ("site-desktop", "SafeTrace KZ · Скрытая игра / 2 минуты\nВидеообзор из снимков работающего интерфейса. Учебные данные; без живой записи."),
    ("site-evidence", "01 · Сообщение → маршрут → основания\n80 — индекс приоритета для аналитика, а не вероятность. Источники доступны по нажатию."),
    ("site-ocr", "02 · Фото и распознанный текст\nOCR выполнен локально. Онлайн-страница показывает сохранённый результат и оригинал."),
    ("site-warning", "03 · Проверка контекста\nПредупреждение получает 0. Совпадение слова «казино» само по себе недостаточно."),
    ("site-network", "04 · Общая сеть публикаций\n96 учебных материалов / 446 сущностей. Группировка по связям не доказывает общего владельца."),
    ("site-metrics", "05 · Проверяемость и следующий шаг\n80 авторских случаев. Независимый реальный тест, усиление KK и OCR ещё нужны."),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/arial.ttf"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.ffmpeg or not args.font.is_file():
        parser.error("Provide ffmpeg and a Unicode TrueType font")
    work = ROOT / "tmp/release-video"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.font, work / "font.ttf")
    concat, filters, sources = [], [], []
    filters.append("scale=1600:980:force_original_aspect_ratio=decrease,pad=1600:1080:(ow-iw)/2:100:color=0x14283e,setsar=1")
    for index, (name, caption) in enumerate(SCENES):
        source = ROOT / "reports/release-2.4/browser" / (name + ".png")
        shutil.copyfile(source, work / (name + ".png"))
        concat.extend([f"file '{name}.png'", "duration 20"])
        (work / f"caption-{index}.txt").write_text(caption, encoding="utf-8", newline="\n")
        filters.append(f"drawtext=fontfile=tmp/release-video/font.ttf:textfile=tmp/release-video/caption-{index}.txt:"
                       f"fontsize=27:fontcolor=white:x=36:y=20:line_spacing=10:enable='gte(t,{index * 20})*lt(t,{(index + 1) * 20})'")
        sources.append({"file": source.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "start_seconds": index * 20, "caption": caption})
    concat.append(f"file '{SCENES[-1][0]}.png'")
    (work / "frames.txt").write_text("\n".join(concat), encoding="utf-8")
    (work / "filters.txt").write_text(",".join(filters), encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-n", "-f", "concat", "-safe", "0",
                    "-i", str(work / "frames.txt"), "-filter_script:v", str(work / "filters.txt"),
                    "-t", "120", "-r", "25", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(args.output)], cwd=ROOT, check=True)
    record = {"format": "Screenshot-based video overview; no live screen recording or audio", "seconds": 120,
              "sources": sources, "bytes": args.output.stat().st_size,
              "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}
    (ROOT / "reports/release-2.4/video.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k != "sources"}))


if __name__ == "__main__":
    main()
