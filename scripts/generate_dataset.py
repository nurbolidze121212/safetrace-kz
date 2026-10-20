"""Author-created synthetic corpus; labels live outside analyzer inputs.

Each family has two controlled variants. No family/template/campaign crosses splits.
The annotations are NOT independent human expert labels.
"""

import hashlib
import json
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets" / "synthetic-v1"

# label, slice, language, destination type, text. These fields NEVER enter analysis.
DEV = [
    (1, "direct", "ru", "game", "Играй в казино, активируй бонус {code}. Сегодня фриспины для новичков."),
    (1, "direct", "kk", "game", "Құмар ойынға тіркел, бонус ал. Ұтысқа мүмкіндік бар. Код {code}."),
    (1, "hidden", "ru", "game", "Закрытый клуб открывает двери. Переходи и забирай бонус {code}. {url}"),
    (1, "hidden", "mixed", "game", "Бүгін мүмкіндік! Переходи по ссылке, бонус с кодом {code}. {url}"),
    (1, "hidden", "kk", "game", "Жаңа алаңға қосыл. Бонус ал, ұсыныс осы жерде: {url}"),
    (
        1,
        "multihop",
        "ru",
        "game",
        "Вечером все самое интересное. Забирай подарок, переходи за бонусом. {url}",
    ),
    (1, "direct", "ru", "game", "Пополняй депозит в слотах и получай бонус. Промокод {code}."),
    (1, "direct", "mixed", "game", "Жми старт: рулетка и бонус ждут! Ұтысқа дайынсың ба? {code}"),
    (1, "unresolved", "ru", "missing", "Заходи за бонусом для друзей. Ссылка открывается ночью: {url}"),
    (1, "translit", "mixed", "game", "Perehodi v nash club, zabirai bonus. Сегодня новый шанс! {url}"),
    (
        0,
        "warning",
        "ru",
        "game",
        "Осторожно: мошенники пишут «играй в казино, забирай бонус». Не переводите деньги. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "game",
        "Алаяқтардан сақ болыңыз! «Тіркел, бонус ал» деген хабарламаға сенбеңіз. {url}",
    ),
    (
        0,
        "news",
        "ru",
        "game",
        "Новость: журналисты изучили рекламу казино с обещанием бонуса. Пример ссылки: {url}",
    ),
    (
        0,
        "education",
        "mixed",
        "game",
        "Сабақ: разбираем схему «переходи, бонус казино». Бұл оқу мысалы. {url}",
    ),
    (
        0,
        "free_game",
        "ru",
        "free",
        "Бесплатная игра без ставок и без вывода денег. Играй в рулетку с учебными жетонами.",
    ),
    (0, "affiliate", "ru", "shop", "Переходи в магазин, забирай бонус на книги. Код {code}. {url}"),
    (0, "ordinary", "kk", "shop", "Кітапханаға келіңіз. Бүгін қазақ әдебиеті туралы кездесу өтеді."),
    (0, "ordinary", "ru", "shop", "Джекпот — название нашего спектакля. Билеты продаются в кассе театра."),
    (0, "ambiguous", "mixed", "missing", "Здесь что-то интересное, говорят знакомые. {url}"),
    (0, "news", "kk", "shop", "Жаңалық: қалада жаңа спорт алаңы ашылды. Балалар тегін қатысады."),
]

TEST = [
    (
        1,
        "direct",
        "ru",
        "game",
        "Слоты на вечер: регистрируйся и получай приветственный бонус по коду {code}.",
    ),
    (1, "direct", "kk", "game", "Рулетка үстеліне қосыл, алғашқы бонус дайын. Арнайы код: {code}."),
    (1, "direct", "mixed", "game", "Казино ашылды! Забирай бонус, тіркел бүгін. Промокод {code}."),
    (1, "direct", "ru", "game", "Для новых гостей казино — бонус. Переходи к регистрации сегодня."),
    (1, "direct", "kk", "game", "Депозит салуға тіркел, сыйлық ал. Бүгінгі ұтыс туралы ақпарат осында."),
    (
        1,
        "hidden",
        "ru",
        "game",
        "Свой круг уже внутри. Заходи по моей ссылке, бонус активируется кодом {code}. {url}",
    ),
    (1, "hidden", "kk", "game", "Тек бүгінгі ұсыныс. Тіркел де бонус ал, мекенжайды сақта: {url}"),
    (1, "hidden", "mixed", "game", "Кешкі жоспар дайын. Жми на приглашение и забирай бонус! {url}"),
    (
        1,
        "hidden",
        "ru",
        "game",
        "Необычное развлечение после работы. Переходи, промокод {code} дает бонус. {url}",
    ),
    (1, "hidden", "kk", "game", "Бізбен бірге баста! Сыйлық сілтемеде, тіркелуге асық: {url}"),
    (
        1,
        "multihop",
        "ru",
        "game",
        "Все спрашивали адрес. Переходи через страницу клуба, получишь бонус {code}. {url}",
    ),
    (
        1,
        "multihop",
        "mixed",
        "game",
        "Біздің парақшада жаңа жол бар. Забирай бонус через кнопку предложения. {url}",
    ),
    (1, "multihop", "kk", "game", "Жеке шақыру: қосыл, сыйлық ал. Серіктес беттен өте аласың: {url}"),
    (1, "translit", "mixed", "game", "Zabirai bonus, perehodi po ssylke. Qazaqsha da bar. {url}"),
    (1, "translit", "ru", "game", "Vecherniy dvizh: kazino, bonus i jackpot. Zaregaysya s kodom {code}."),
    (1, "unresolved", "ru", "missing", "Место встречи поменялось. Переходи за бонусом в новый клуб: {url}"),
    (1, "unresolved", "kk", "missing", "Бүгін ғана тіркел, бонус ал. Ескі сілтеме істемесе, күте тұр: {url}"),
    (
        1,
        "contradictory",
        "ru",
        "game",
        "Осторожно, азарт затягивает. Но переходи и забирай бонус в казино прямо сейчас! {url}",
    ),
    (1, "direct", "ru", "game", "Играй в слоты: обещаем выигрыш и приветственные фриспины каждому гостю."),
    (1, "hidden", "mixed", "game", "Твой шанс на ұтыс. Переходи сюда и забирай бонус от команды. {url}"),
    (
        0,
        "warning",
        "ru",
        "game",
        "Памятка: осторожно, фраза «заходи в казино за бонусом» — приманка мошенников. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "game",
        "Сақ бол! Алаяқтар «бонус ал, тіркел» деп жазады. Ақша жібермеңіз. Мысал: {url}",
    ),
    (0, "warning", "mixed", "game", "Это скам: «переходи и получи бонус в слотах». Сілтемеге өтпеңіз. {url}"),
    (
        0,
        "warning",
        "ru",
        "game",
        "Не играйте по чужим ссылкам. Мошенники обещают выигрыш и бонус казино: {url}",
    ),
    (
        0,
        "news",
        "ru",
        "game",
        "Корреспондент изучил, как блогеры пишут «забирай бонус в казино». Адрес из публикации: {url}",
    ),
    (
        0,
        "news",
        "kk",
        "game",
        "Жаңалық: мамандар құмар ойын жарнамасын зерттеді. Мақалада бонус туралы мысал бар. {url}",
    ),
    (
        0,
        "news",
        "mixed",
        "game",
        "Редакция сообщает новость: рекламу «играй, бонус казино» обсуждают на конференции. {url}",
    ),
    (
        0,
        "education",
        "ru",
        "game",
        "Образовательный разбор: почему «переходи в казино, забирай бонус» нельзя считать надежным обещанием. {url}",
    ),
    (0, "education", "kk", "game", "Медиасауат сабағы. «Тіркел, бонус ал» деген жарнаманы талдаймыз. {url}"),
    (
        0,
        "education",
        "mixed",
        "game",
        "На уроке сравниваем выражения «играй в казино» и «изучи риски». Бұл сабақ, жарнама емес.",
    ),
    (
        0,
        "free_game",
        "ru",
        "free",
        "Поиграем в учебные слоты: бесплатная игра без денежных ставок. Играй и получай бонусные очки.",
    ),
    (0, "free_game", "kk", "free", "Тегін ойын, ақшасыз рулетка. Қосыл, бонус ұпайларын ал. Ақша төлеу жоқ."),
    (
        0,
        "affiliate",
        "ru",
        "shop",
        "Для читателей новый бонус: переходи за скидкой на словари. Промокод {code}. {url}",
    ),
    (
        0,
        "affiliate",
        "mixed",
        "shop",
        "Киім дүкені: забирай бонус при покупке куртки. Біздің серіктес сілтемеміз: {url}",
    ),
    (0, "ordinary", "ru", "shop", "Волонтеры открывают клуб настольных игр. Приносите шахматы и друзей."),
    (
        0,
        "ordinary",
        "kk",
        "shop",
        "Әңгіме кешіне шақырамыз. Ғалымдар, қонақтар, өңір тарихы және ұлттық өнер.",
    ),
    (
        0,
        "ordinary",
        "mixed",
        "shop",
        "Бонус к зарплате начислен. Құттықтаймыз! Никаких регистраций и переводов.",
    ),
    (
        0,
        "ambiguous",
        "ru",
        "missing",
        "Короткая ссылка без пояснений. Автор пишет только «смотри сюда». {url}",
    ),
    (0, "ambiguous", "kk", "missing", "Не екені белгісіз. Жай ғана мекенжай: {url}"),
    (0, "ambiguous", "mixed", "shop", "Промокод {code}. Больше информации нет, источник пока неизвестен."),
]

PAGES = {
    "game": "<h1>Клуб</h1><p>Слоты, рулетка, депозит и фриспины. Синтетический макет; платежей нет.</p>",
    "shop": "<h1>Магазин</h1><p>Книги, одежда, скидки и партнерская программа. Синтетический макет.</p>",
    "free": "<h1>Учебная игра</h1><p>Бесплатные упражнения без ставок и без вывода денег.</p>",
}


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    annotations, all_pages, split_inputs = [], {}, {}
    font_path = "C:/Windows/Fonts/arial.ttf"
    for split, families in (("dev", DEV), ("test", TEST)):
        inputs, pages = [], {}
        for family, (label, category, language, target, text) in enumerate(families):
            for variant in range(2):
                seed = hashlib.sha256(f"safetrace-v1|{split}|{family}|{variant}".encode()).hexdigest()
                rng = random.Random(seed)
                rid = seed[:16]
                code = "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))
                host = hashlib.sha256(f"site|{split}|{family}".encode()).hexdigest()[:9]
                start = f"https://n{host}.test/s/{variant}"
                hub = f"https://m{host}.test/info/{variant}"
                end = f"https://p{host}.test/offer?ref={code}"
                body = text.format(code=code, url=start)
                if variant == 1:
                    body = "DEMO · " + body
                # Image placement and quality independent of truth, random IDs have no class hints.
                image = None
                if (family * 2 + variant) % 3 == 0:
                    font = ImageFont.truetype(font_path, 24 if family % 4 else 19)
                    wrapped = "\n".join(textwrap.wrap(body, 69, break_long_words=False))
                    height = 70 + (len(wrapped.splitlines()) + 1) * 39
                    im = Image.new("RGB", (1050, height), (248, 249, 246))
                    draw = ImageDraw.Draw(im)
                    draw.multiline_text((30, 25), wrapped, font=font, fill=(20, 34, 28), spacing=12)
                    if family % 5 == 0:
                        im = im.rotate(3, expand=True, fillcolor=(248, 249, 246))
                    image = f"images/{rid}.jpg"
                    im.save(OUT / image, quality=60 if family % 4 == 0 else 88)
                source = "author-" + hashlib.sha256(f"{split}-{family}".encode()).hexdigest()[:7]
                material = {
                    "text": "" if image else body,
                    "url": "",
                    "source": source,
                    "published_at": "2026-10-19T14:00:00+05:00",
                    "image": image,
                }
                inputs.append({"id": rid, "materials": [material]})
                if target != "missing":
                    pages[start] = {"status": 302, "headers": {"location": hub}}
                    pages[hub] = {
                        "status": 200,
                        "body": f'<p>Информация для посетителя.</p><a href="{end}">Открыть страницу</a>',
                    }
                    pages[end] = {"status": 200, "body": PAGES[target]}
                annotations.append(
                    {
                        "id": rid,
                        "split": split,
                        "family": f"{split}-{family}",
                        "truth": label,
                        "category": category,
                        "language": language,
                        "image": bool(image),
                        "reference_text": body,
                        "expected_destination": end if "{url}" in text and target != "missing" else None,
                        "annotation_origin": "author-created synthetic; not independent expert review",
                    }
                )
        split_inputs[split] = inputs
        (OUT / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in inputs) + "\n", encoding="utf-8"
        )
        (OUT / f"{split}-pages.json").write_text(
            json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        all_pages.update(pages)
    (OUT / "annotations.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in annotations) + "\n", encoding="utf-8"
    )
    assert len(annotations) == 120 and sum(x["image"] for x in annotations) >= 30
    assert not {x["family"] for x in annotations if x["split"] == "dev"} & {
        x["family"] for x in annotations if x["split"] == "test"
    }
    print(
        json.dumps(
            {"cases": 120, "dev": 40, "test": 80, "images": sum(x["image"] for x in annotations)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    build()
