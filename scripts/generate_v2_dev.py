"""New author-labelled development corpus; no held-out test cases are defined here."""

import hashlib
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/synthetic-v2"
# truth, category, language, destination content, hop count, authored source.
CASES = [
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "DEMO. У нас открыт зал казино. Регистрируйтесь и активируйте бонус по коду {code}.",
    ),
    (
        1,
        "direct",
        "kk",
        "game",
        0,
        "DEMO. Слот ойындарына тіркеліңіз. Жаңа қатысушыға бонус дайын, код {code}.",
    ),
    (1, "direct", "mixed", "game", 0, "DEMO. Рулетка кеші басталды. Қосыл, забирай бонус на первый раунд."),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "DEMO. Подборка вечерних предложений: переходите через приглашение, забирайте бонус. {url}",
    ),
    (1, "hidden", "kk", "game", 1, "DEMO. Жеке ұсынысты көру үшін өтіңіз. Тіркел де сыйлығыңды ал. {url}"),
    (
        1,
        "hidden",
        "mixed",
        "game",
        1,
        "DEMO. Арнайы клубқа қосыл! Бонус доступен по моему приглашению. {url}",
    ),
    (
        1,
        "multihop",
        "ru",
        "game",
        3,
        "DEMO. Жми на карточку предложения, затем забирай бонус в личном зале. {url}",
    ),
    (
        1,
        "multihop",
        "kk",
        "game",
        3,
        "DEMO. Ұсыныс парағына өтіңіз, одан кейін тіркеліп сыйлық алыңыз. {url}",
    ),
    (1, "translit", "other", "game", 0, "DEMO. Zaregaysya v kazino, bonus po kodu {code}."),
    (1, "translit", "other", "game", 2, "DEMO. Tirkel, bonus al. Qosyl, kazino osynda: {url}"),
    (1, "direct", "ru", "game", 0, "DEMO. Заходите в казино и играйте сегодня. Приглашаем новых участников."),
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "DEMO. Жмите: слоты, рулетка и фриспины для вас. Активируйте промокод {code}.",
    ),
    (1, "direct", "mixed", "game", 0, "DEMO. Ұтысқа дайын бол! Играй в казино, забирай бонус, код {code}."),
    (
        1,
        "contradictory",
        "ru",
        "game",
        1,
        "DEMO. Осторожно с чужими предложениями. Но переходи по моей ссылке, забирай бонус в казино. {url}",
    ),
    (
        1,
        "contradictory",
        "kk",
        "game",
        1,
        "DEMO. Алаяқтардан сақ бол. Бірақ біздің казиноға тіркел, бонус ал! {url}",
    ),
    (
        1,
        "unresolved",
        "ru",
        "missing",
        1,
        "DEMO. Приватное приглашение еще доступно. Переходи, забирай бонус. {url}",
    ),
    (1, "hidden", "kk", "game", 1, "DEMO. Мына жерде кешкі сыйлық пен қызықты ұсыныс бар. Мекенжай: {url}"),
    (1, "direct", "ru", "game", 0, "DEMO. Играй в слоты, получай фриспины. Забирай промокод {code}."),
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "DEMO. 🎲 Не переходи по чужим ссылкам. Но переходи в наше казино, бонус для новых гостей!",
    ),
    (
        1,
        "unresolved",
        "kk",
        "missing",
        1,
        "DEMO. Кіру үшін тіркел, сыйлық ал. Сілтеме уақытша ашылмайды: {url}",
    ),
    (
        0,
        "warning",
        "ru",
        "game",
        1,
        "DEMO. Памятка: осторожно, мошенники зовут «регистрируйтесь в казино, бонус ждет». Не играйте. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "game",
        1,
        "DEMO. Сақ болыңыз: «Қосыл, бонус ал» дегенге сенбеңіз. Құмар ойынға тіркелмеңіз. {url}",
    ),
    (
        0,
        "news",
        "ru",
        "game",
        1,
        "DEMO. Корреспондент приводит цитату из рекламы: «Жми и забирай бонус в казино». Это новость о проверке рекламы. {url}",
    ),
    (
        0,
        "education",
        "kk",
        "game",
        1,
        "DEMO. Медиасауат сабағында «Тіркел, бонус ал» деген сөйлемді талдаймыз. Бұл оқу мысалы. {url}",
    ),
    (
        0,
        "education",
        "mixed",
        "game",
        0,
        "DEMO. Сабақтың тақырыбы — скрытая реклама. Учебный пример: «Играй в казино, бонус ал».",
    ),
    (
        0,
        "free_game",
        "ru",
        "free",
        1,
        "DEMO. Играй в бесплатную рулетку с жетонами. Без ставок, без денежных платежей и без вывода денег. {url}",
    ),
    (
        0,
        "free_game",
        "kk",
        "free",
        0,
        "DEMO. Тегін ойынға қосыл. Ақшасыз ойын, ұтыс жоқ. Сабақ үшін қолданамыз.",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        1,
        "DEMO. Регистрируйтесь в банке: депозит и бонус за обслуживание. Договор вклада доступен здесь. {url}",
    ),
    (
        0,
        "affiliate",
        "ru",
        "shop",
        2,
        "DEMO. Книжная подписка: переходи и забирай бонус на новый роман. Промокод {code}. {url}",
    ),
    (
        0,
        "affiliate",
        "kk",
        "shop",
        1,
        "DEMO. Киім дүкеніне тіркел, сатып алуға сыйлық алыңыз. Мекенжай: {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        0,
        "DEMO. Это материал о ремонте. В слове материал нет призыва. Фестиваль состоится завтра.",
    ),
    (
        0,
        "ordinary",
        "kk",
        "shop",
        0,
        "DEMO. Мектептің жаңа сабағы ертең өтеді. Ата-аналарға ақпарат беріледі.",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        0,
        "DEMO. Играй в спектакле «Казино» нашего театра: набор актеров, бонус участникам.",
    ),
    (0, "ordinary", "ru", "shop", 0, "DEMO. Переходи за ноутбуком: два слота памяти и бонус на аксессуары."),
    (
        0,
        "warning",
        "ru",
        "missing",
        1,
        "DEMO. Не переходите по этой ссылке, не забирайте обещанный бонус. Осторожно, мошенники. {url}",
    ),
    (
        0,
        "news",
        "kk",
        "shop",
        1,
        "DEMO. Жаңалық: жаңа кітап орталығы ашылды. Редакция хабарлайды, жоба туралы мәлімет: {url}",
    ),
    (
        0,
        "education",
        "ru",
        "game",
        0,
        "DEMO. Урок медиаграмотности. Фраза «Но переходи в казино, забирай бонус» — пример манипуляции.",
    ),
    (
        0,
        "ordinary",
        "mixed",
        "shop",
        0,
        "DEMO. Ұтыс ойыны туралы ескерту: бұл мектептің тегін викторинасы, ақшасыз. Бонус — кітап.",
    ),
    (
        0,
        "ambiguous",
        "ru",
        "missing",
        1,
        "DEMO. Получил непонятное сообщение, проверенных сведений пока нет. {url}",
    ),
    (
        0,
        "ambiguous",
        "kk",
        "missing",
        1,
        "DEMO. Бұл мекенжайдың мазмұны белгісіз. Қосымша деректер қажет. {url}",
    ),
]


def ident(value):
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def build():
    if (OUT / "dev.jsonl").exists():
        raise RuntimeError("Dev corpus already exists. Change it explicitly with versioned evidence.")
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    inputs, labels, pages = [], [], {}
    for i, (truth, category, language, destination, hops, template) in enumerate(CASES):
        token = ident("night-v2-development-material-" + str(i))
        host = "https://n" + ident(token + "host")[:10] + ".test"
        code = "K" + ident(token + "ref")[:6].upper()
        destination_url = host + "/space/" + ident(token + "path")[:6] + "?ref=" + code
        url = host + "/visit/" + ident(token + "entry")[:6] if hops else destination_url
        text = template.format(url=url, code=code)
        if destination != "missing":
            content = {
                "game": "<h1>DEMO: развлекательный зал</h1><p>Казино: слоты, рулетка, фриспины. Бонус для новых игроков. Платежи отсутствуют.</p>",
                "shop": "<h1>DEMO: каталог</h1><p>Книги, одежда и обычные услуги. Бонус по программе магазина.</p>",
                "free": "<h1>DEMO: учебная игра</h1><p>Тегін ойын. Бесплатная рулетка без ставок, без вывода денег, с учебными жетонами.</p>",
            }[destination]
            pages[destination_url] = {"status": 200, "body": content}
            if hops:
                chain = (
                    [url]
                    + [host + "/step/" + ident(token + str(j))[:6] for j in range(hops - 1)]
                    + [destination_url]
                )
                for j, (source, target) in enumerate(zip(chain, chain[1:])):
                    pages[source] = (
                        {"status": 302, "headers": {"location": target}}
                        if j % 2 == 0
                        else {
                            "status": 200,
                            "body": '<p>DEMO. Условия предложения.</p><a href="'
                            + target
                            + '">Открыть карточку</a>',
                        }
                    )
        image_name = None
        if i % 5 in (0, 2):
            small = i in (17, 37)
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 21 if small else 29)
            lines = textwrap.wrap(text, width=72 if small else 58, break_long_words=False)
            image = Image.new("RGB", (1100, 80 + len(lines) * 48), "#f8fafc")
            draw = ImageDraw.Draw(image)
            for j, line in enumerate(lines):
                draw.text((32, 28 + j * 48), line, font=font, fill="#1c3046")
            rotation = 90 if i in (5, 25) else 180 if i in (12, 32) else 0
            image = image.rotate(rotation, expand=True, fillcolor="#f8fafc")
            image_name = "images/" + ident(token + "pixels") + ".jpg"
            image.save(OUT / image_name, quality=48 if small else 87)
        inputs.append(
            {
                "id": token,
                "materials": [
                    {
                        "text": "" if image_name else text,
                        "url": "",
                        "source": "DEMO · материал " + token[:5],
                        "image": image_name,
                    }
                ],
            }
        )
        labels.append(
            {
                "id": token,
                "split": "dev",
                "truth": truth,
                "category": category,
                "language": language,
                "image": bool(image_name),
                "family": "dev-" + ident(token + "family"),
                "campaign": ident(token + "campaign"),
                "domains": [host],
                "reference_text": text,
                "annotation_provenance": "Author-created synthetic label; no independent expert validation.",
            }
        )
    (OUT / "dev.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in inputs) + "\n", encoding="utf-8"
    )
    (OUT / "dev-annotations.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in labels) + "\n", encoding="utf-8"
    )
    (OUT / "dev-pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "cases": len(inputs),
                "images": sum(row["image"] for row in labels),
                "positive": sum(row["truth"] for row in labels),
                "pages": len(pages),
            }
        )
    )


if __name__ == "__main__":
    build()
