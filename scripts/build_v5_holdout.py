"""Author 640 synthetic cases only after the inference contract is frozen."""

import hashlib
import html
import json
import textwrap
from collections import Counter
from pathlib import Path

from evaluate_v5 import hashes
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/synthetic-v5"
FREEZE = ROOT / "reports/versions/synthetic-v5/core-freeze.json"

POS = {
    "ru": [
        "Открылся игровой зал: играй в казино и пополни депозит сегодня.",
        "Личный кабинет уже готов. Переходи по приглашению и забирай подарок после регистрации.",
        "На стриме показал вывод выигрыша. Подключайся к моему казино, начинай играть.",
        "К@зино даёт фриспины. Регистрируйся по моему приглашению.",
        "К а з и н о зовёт: забирай бонус и играй на деньги.",
        "К🅰️зино открыло набор. Играй в слоты, первый бонус ждёт.",
        "Вот скрин моего выигрыша в слотах. Переходи ко мне и играй.",
        "Промокод NURA9 для казино. Забирай бонус, регистрируйся.",
        "Осторожно, чужие площадки опасны. Но в нашем казино играй и получай бонус.",
        "Закрытая комната ждёт участников. Переходи, регистрируйся, получи фриспины.",
        "Сначала канал, потом страница: играй в рулетку, забирай бонус по ссылке.",
    ],
    "kk": [
        "Құмар ойын залы ашылды. Казиноға тіркел, ақша салып ойнаңыз.",
        "Жеке кабинет дайын. Сілтемеге өтіп, тіркеліңіз де сыйлық алыңыз.",
        "Тікелей эфирде ұтысымды көрсеттім. Казиноға қосылыңыз, ойнаңыз.",
        "К@зино бонус береді. Біздің шақырумен тіркеліңіз.",
        "К а з и н о: бүгін тіркел, ақшалай ұтысқа ойнаңыз.",
        "К🅰️зиноға қосыл. Слот ойнаңыз, алғашқы бонус күтіп тұр.",
        "Слоттан ақша шығардым. Сен де тіркел, ойна.",
        "NURA9 промокоды казино үшін. Бонус алып, тіркеліңіз.",
        "Алаяқтан сақ болыңыз. Бірақ біздің казиноға тіркел, бонус ал.",
        "Жабық топқа қосылыңыз. Тіркеліп, фриспин алыңыз.",
        "Әуелі арна, кейін ойын беті: рулетка ойна, бонус ал.",
    ],
    "translit": [
        "Qumar oiyn zaly ashyldy. Kazino tirkel, aqsha salyp oina.",
        "Jeke kabinet dayyn. Siltemege otip, tirkel de syilyq al.",
        "Tikelei efirde utys korsetim. Kazino qosyl da oina.",
        "K@zino bonus beredi. Bizdin shaqyrumen tirkel.",
        "K a z i n o: bugin tirkel, aqshalyq utysqa oina.",
        "K🅰️zino qosyl. Slot oina, algashqy bonus kutip tur.",
        "Slottan aqsha shygarдым. Sen de tirkel, oina.",
        "NURA9 promo kody kazino ushin. Bonus alyp tirkel.",
        "Alaiaqtan saq bol. Biraq bizdin kazino tirkel, bonus al.",
        "Jabyq topqa qosyl. Tirkelip free spin al.",
        "Aueli arna, keyin oiyn beti: ruletka oina, bonus al.",
    ],
    "mixed": [
        "Құмар ойын залы открылся. Казиноға тіркел, пополни депозит и играй.",
        "Жеке кабинет готов. Переходи по ссылке, тіркел де сыйлық ал.",
        "Эфирде ұтысымды көрсеттім. Подключайся к казино и ойна.",
        "К@зино бонус береді. Регистрируйся по приглашению.",
        "К а з и н о: бүгін тіркел, играй на деньги.",
        "К🅰️зиноға қосыл. Играй в слоты, бонус ждёт.",
        "Слоттан деньги вывел. Переходи, тіркел, ойна.",
        "NURA9 промокоды для казино. Бонус ал, регистрируйся.",
        "Алаяқтан сақ болыңыз. Но в нашем казино ойна и получай бонус.",
        "Жабық топ ждёт. Тіркеліп, получи фриспины.",
        "Әуелі арна, потом игра: рулетка ойна, забирай бонус.",
    ],
}
NEG = {
    "ru": [
        "Честный бесплатный конкурс. Победителя выберем случайно; никакой оплаты и ставок.",
        "Редакция публикует новость о рекламе казино. Это журналистский материал, без приглашения играть.",
        "Предупреждение: казино и быстрый выигрыш в чужих сообщениях. Не регистрируйтесь и не платите.",
        "Легальная реклама магазина: бонус за покупку товаров, запись на свободный слот консультации.",
        "Урок медиаграмотности: фраза «играй в казино» приведена как пример вредной рекламы.",
    ],
    "kk": [
        "Тегін адал байқау. Жеңімпаз кездейсоқ анықталады; ақша салу керек емес.",
        "Редакция казино жарнамасы туралы жаңалық жазды. Бұл мақала, ойнауға шақырмайды.",
        "Ескерту: казиноға тіркелмеңіз, ақша салмаңыз, құмар ойын ойнамаңыз.",
        "Дүкеннің заңды жарнамасы: киімге жеңілдік, бонус бар. Ойын емес.",
        "Сабақта «казиноға тіркел» деген жалған жарнаманы талдаймыз. Бұл ескерту.",
    ],
    "translit": [
        "Tegin adal baiqau. Jenimpaz kezdeisoq tandalady; aqsha salu kerek emes.",
        "Redakciya kazino jarnamasy turaly zhanalyq zhazdy. Bul maqala, oinauga shaqyrmaidy.",
        "Eskertu: kazino tirkelme, aqsha salma, qumar oiyn oinama.",
        "Duken zandy jarnama zhasaidy: kiimge zhenildik, bonus bar. Oiyn emes.",
        "Sabaqta kazino tirkel degen zhalgan jarnamany taldaimyz. Bul eskertu.",
    ],
    "mixed": [
        "Тегін адал конкурс: случайный победитель, взнос жоқ, ставок нет.",
        "Редакция жазды новость о рекламе казино. Бұл мақала, не приглашение играть.",
        "Ескерту: не регистрируйся в казино, ақша салмаңыз, ойнамаңыз.",
        "Дүкен предлагает скидку на одежду и бонус. Казино емес, ойын жоқ.",
        "Сабақта фразу «играй в казино» разбираем как вредный пример. Бұл ескерту.",
    ],
}
NEG_CATEGORY = (["contest"] * 4 + ["news"] * 4 + ["warning"] * 5 + ["business"] * 4 + ["education"] * 4)
CATEGORIES = ["contest", "news", "warning", "business", "education"]


def main():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert freeze["analysis_hashes"] == hashes(ROOT), "The classifier differs from its freeze"
    assert not OUT.exists(), "Hold-out is immutable; do not regenerate"
    (OUT / "images").mkdir(parents=True)
    font_path = next(p for p in [Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")] if p.exists())
    font = ImageFont.truetype(str(font_path), 23)
    inputs, author, blind, pages = [], [], [], {}
    for language in ("ru", "kk", "translit", "mixed"):
        assert len(POS[language]) == 11 and len(NEG[language]) == 5
        for family in range(32):
            truth = int(family < 11)
            category = "promotion" if truth else NEG_CATEGORY[family - 11]
            base = POS[language][family] if truth else NEG[language][CATEGORIES.index(category)]
            for variant in range(5):
                key = hashlib.sha256(f"final-v5/{language}/{family}/{variant}".encode()).hexdigest()[:20]
                url = f"https://m{key[:12]}.test/start"
                has_url = family in {1, 2, 6, 8, 9, 11, 12, 15, 16, 19, 21, 23, 26, 29}
                text = base + (" " + url if has_url else "") + f"\nАрхив {family + 1}.{variant + 1}"
                image = variant == 0 or (variant == 1 and family < 8)
                material = {"text": text, "source": "Авторский синтетический материал v5"}
                if image:
                    lines = textwrap.wrap(text, width=48, break_long_words=False)
                    picture = Image.new("RGB", (790, 80 + 39 * len(lines)), "#f8fafc")
                    draw = ImageDraw.Draw(picture)
                    for row, line in enumerate(lines):
                        draw.text((24, 20 + 39 * row), line, font=font, fill="#172641")
                    picture.save(OUT / "images" / (key + ".jpg"), quality=72)
                    material = {"text": "", "source": "Авторский синтетический скриншот v5", "image": "images/" + key + ".jpg"}
                destination = None
                if has_url:
                    destination = ("Играй в казино, слоты на деньги. Регистрируйся и пополни депозит."
                                   if truth else {"contest": "Конкурс книг, бесплатно. Победитель получит книгу.",
                                                  "news": "Редакционное расследование о рекламе казино. Не призыв играть.",
                                                  "warning": "Предупреждение о вреде казино. Не переходите к рекламе.",
                                                  "business": "Легальный магазин одежды. Бонус за покупку, азартных игр нет.",
                                                  "education": "Учебный разбор примеров рекламы казино."}[category])
                    pages[url] = {"status": 200, "body": "<p>" + html.escape(destination) + "</p>"}
                inputs.append({"id": key, "materials": [material]})
                author.append({"id": key, "truth": truth, "language": language, "modality": "image" if image else "text",
                               "image": image, "family": f"{language}/{family}", "masking":
                               (["direct", "redirect", "stream", "homoglyph", "spacing", "emoji", "story", "promo", "contrast", "private_group", "multi_step"][family] if truth else category),
                               "reference_text": text, "author_intent": category,
                               "provenance": "Author-created synthetic intention; not an independent label"})
                blind.append({"id": key, "message": text if not image else None,
                              "author_transcription_of_screenshot": text if image else None,
                              "destination_observed_in_synthetic_stand": destination,
                              "modality": "screenshot_with_author_transcription" if image else "text"})
    for name, rows in (("inputs.jsonl", inputs), ("annotations.jsonl", author), ("blind.jsonl", blind)):
        (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    (OUT / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    counts = Counter((x["language"], x["modality"], x["truth"]) for x in author)
    assert len(inputs) == len(author) == len(blind) == 640 and sum(x["truth"] for x in author) == 220
    assert sum(x["image"] for x in author) == 160 and all(sum(x["language"] == language for x in author) == 160 for language in POS)
    (OUT / "PROVENANCE.md").write_text(
        "# Synthetic v5 provenance\n\nCreated after classifier freeze on " + freeze["at"] + ". 640 authored cases; 220 intended positives, 420 intended hard negatives, 160 screenshots. All domains are .test and pages are authored fixtures. Screenshot transcriptions are authored and are supplied only to blind LLM labelers, never to inference. The cases are template-related and are not independent real-world samples. Author intent is separate from LLM adjudicated labels.\n", encoding="utf-8", newline="\n")
    print(json.dumps({"cases": len(inputs), "positive_author_intent": 220, "negative_author_intent": 420,
                      "images": 160, "strata": {str(k): v for k, v in counts.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
