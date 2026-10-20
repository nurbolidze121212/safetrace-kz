"""Author a new final synthetic corpus only after the v2 core has been frozen.

Each row is a separately authored source template, not a reskin of dev. Labels are
author judgements, not independent expert adjudication. No classifier is imported.
"""

import hashlib
import json
import re
import textwrap
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/synthetic-v2"
# truth, category, language, destination, hops, complete independently authored source
CASES = [
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "Вечерний эфир переехал в казино. Присоединяйся к игре за столом рулетки, приглашение {code}.",
    ),
    (
        1,
        "direct",
        "kk",
        "game",
        0,
        "Достар, бүгін казино залында кездесейік. Тіркеліңіз де алғашқы айналымға бонус алыңыз.",
    ),
    (
        1,
        "direct",
        "mixed",
        "game",
        0,
        "Сенің кезегің! Играй в слоты на нашей площадке, фриспины ждут новых участников.",
    ),
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "В клубе снова открыта рулетка на деньги. Жми на регистрацию, получай стартовый пакет.",
    ),
    (1, "direct", "kk", "game", 0, "Казиноға жаңа қонақтарды шақырамыз. Қосыл, кодты енгіз: {code}."),
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "Любишь игровые автоматы? Переходи в казино, сегодня каждому новичку дают бонус.",
    ),
    (
        1,
        "direct",
        "mixed",
        "game",
        0,
        "Қош келдің! Казино ашық. Регистрируйся и забирай промокод на первый вечер.",
    ),
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "Участники моего канала, играйте в рулетку вместе со мной. Активация бонуса по коду {code}.",
    ),
    (1, "hidden", "kk", "game", 2, "Кешкі кездесуге шақыру осы карточкада. Қосыл да сыйлық ал: {url}"),
    (
        1,
        "direct",
        "mixed",
        "game",
        0,
        "Бүгін жаңа слот шықты. Играй сейчас, стартовый бонус можно забрать после регистрации.",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "Обещанный адрес закрытого клуба отправляю здесь. Регистрируйся, пакет для первого визита уже готов. {url}",
    ),
    (
        1,
        "hidden",
        "kk",
        "game",
        1,
        "Жеке кабинетке жол ашылды. Өтіңіз, тіркеліңіз, қосымша сыйлық алыңыз. {url}",
    ),
    (
        1,
        "hidden",
        "mixed",
        "game",
        2,
        "Сілтемені сақтап ал. Жми на приглашение и получай бонус после входа в клуб. {url}",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "Подписчикам доступна секретная вечерняя акция. Переходи к партнеру, забирай свой подарок. {url}",
    ),
    (
        1,
        "hidden",
        "kk",
        "game",
        1,
        "Бүгінгі ұсыныстың шарттары жеке бетте тұр. Қатысу үшін қосыл, код {code}. {url}",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "Выбирайте карточку с моим приглашением. Регистрируйтесь на площадке и активируйте бонус. {url}",
    ),
    (
        1,
        "hidden",
        "mixed",
        "game",
        2,
        "Жаңа мүмкіндік ашылды: переходите в личный кабинет, алғашқы бонус дайын. {url}",
    ),
    (
        1,
        "hidden",
        "kk",
        "game",
        1,
        "Арнайы парақтағы кешке тіркел. Сыйлықты алу үшін төмендегі мекенжайға өтіңіз. {url}",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "Доступ к предложению остается до полуночи. Жми, забирай начисление на первый раунд. {url}",
    ),
    (
        1,
        "hidden",
        "mixed",
        "game",
        1,
        "Клубқа шақыру келді. Приглашаем зарегистрироваться и получить бонус по карточке. {url}",
    ),
    (
        1,
        "multihop",
        "ru",
        "game",
        3,
        "Сначала открой подборку, затем приглашение партнера. Переходи и играй, бонус закреплен за ссылкой. {url}",
    ),
    (
        1,
        "multihop",
        "kk",
        "game",
        4,
        "Алдымен ақпарат бетін ашыңыз, одан әрі клубқа қосыл. Бонусты сол жерден алуға болады. {url}",
    ),
    (
        1,
        "multihop",
        "mixed",
        "game",
        3,
        "Екі беттен кейін ұсыныс ашылады. Жми на кнопку партнера, тіркел де бонус ал. {url}",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        2,
        "Ваше приглашение спрятано в карточке. Регистрируйся по ней, забирай дополнительный бонус. {url}",
    ),
    (
        1,
        "multihop",
        "kk",
        "game",
        3,
        "Жол көрсетілген парақ арқылы өтіңіз. Соңғы бетте тіркеліп, сыйлық алыңыз. {url}",
    ),
    (
        1,
        "multihop",
        "ru",
        "game",
        4,
        "Мой партнер перенес акцию на новую страницу. Переходи по цепочке и активируй бонус в конце. {url}",
    ),
    (
        1,
        "multihop",
        "mixed",
        "game",
        3,
        "Карточканы ашып, келесі батырманы таңда. Играй на площадке партнера, бонус уже доступен. {url}",
    ),
    (
        1,
        "contradictory",
        "ru",
        "game",
        1,
        "Не доверяйте чужим обещаниям. Но играйте в нашем казино: я даю личный бонус новым гостям. {url}",
    ),
    (
        1,
        "contradictory",
        "kk",
        "game",
        1,
        "Күмәнді жарнамадан сақ болыңыз. Бірақ осы казиноға қосыл, бүгін бонус беріледі. {url}",
    ),
    (
        1,
        "contradictory",
        "mixed",
        "game",
        0,
        "Бұл ескерту бәріне ортақ. Но регистрируйся в казино нашего партнера и забирай подарок.",
    ),
    (
        1,
        "contradictory",
        "ru",
        "game",
        0,
        "Мы обсуждали мошенников на стриме. Однако заходи в казино по моему коду {code}, получай фриспины.",
    ),
    (
        1,
        "unresolved",
        "ru",
        "missing",
        1,
        "Приглашение в закрытый денежный клуб. Жми и забирай приветственный бонус. {url}",
    ),
    (
        1,
        "unresolved",
        "kk",
        "missing",
        1,
        "Жабық клубқа тіркелуге болады. Кешкі сыйлықты алу үшін өтіңіз. {url}",
    ),
    (
        1,
        "unresolved",
        "mixed",
        "missing",
        1,
        "Ойын кешіне шақыру: переходи, бонус беріледі. Страница пока отвечает с ошибкой. {url}",
    ),
    (
        1,
        "unresolved",
        "ru",
        "missing",
        1,
        "Твой доступ к партнерской игре ждет. Регистрируйся по приглашению, забирай бонус. {url}",
    ),
    (
        1,
        "translit",
        "other",
        "game",
        0,
        "Kazino vecherom otkryto: zaregaysya, poluchi bonus i igray v ruleтку.",
    ),
    (1, "translit", "other", "game", 1, "Dostar, qosyl! Tirkel de bonus al, klubqa jol osynda. {url}"),
    (
        1,
        "hidden",
        "kk",
        "game",
        1,
        "Кешкі топтың жаңа мекені төменде. Қалаған адамға жеке сыйлық қарастырылған. {url}",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "Любимый ведущий уже там, подарок внутри личного кабинета. Адрес оставлю под постом. {url}",
    ),
    (
        1,
        "direct",
        "kk",
        "game",
        0,
        "Құмар ойын кеші басталды, рулетка үстелі дайын. Тіркел, алғашқы бонус сені күтеді.",
    ),
    (
        0,
        "warning",
        "ru",
        "game",
        1,
        "Родители, будьте осторожны: сообщение «Играй в казино и забирай бонус» ведет на опасную страницу. Не регистрируйтесь. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "game",
        1,
        "Ескерту: мына жарнамадағы «тіркел де бонус ал» сөзіне сенбеңіз. Құмар ойынға қосылмаңыз. {url}",
    ),
    (
        0,
        "warning",
        "mixed",
        "game",
        1,
        "Сақ бол! В сообщении обещают фриспины и зовут играть. Это пример мошенничества, а не рекомендация. {url}",
    ),
    (
        0,
        "warning",
        "ru",
        "game",
        2,
        "Памятка подписчику: фразу «Жми на казино, получай подарок» используют мошенники. Не открывайте приглашение. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "game",
        1,
        "Алаяқтар бонуспен қызықтырады. Тіркелмеңіз, ақша аудармаңыз, күмәнді мекенжайды тек маман тексерсін. {url}",
    ),
    (
        0,
        "warning",
        "ru",
        "game",
        1,
        "Осторожно, поддельный розыгрыш приводит к казино. Призыв «заходи и играй» приведен для распознавания обмана. {url}",
    ),
    (
        0,
        "warning",
        "mixed",
        "game",
        1,
        "Бұл қауіп туралы хабарлама. Не играйте в казино по этой рекламе и не забирайте обещанный бонус. {url}",
    ),
    (
        0,
        "warning",
        "ru",
        "game",
        1,
        "Если вам пишут «регистрируйся, казино начислит бонус», остановитесь. Мошенничество нужно сообщить модератору. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "game",
        2,
        "Сақ болыңыз: карточка белгісіз ойын залына апарады. «Қосыл, бонус ал» деген шақыруды қайталамаңыз. {url}",
    ),
    (
        0,
        "warning",
        "ru",
        "missing",
        1,
        "Осторожно с заблокированным приглашением. Не переходи, не играй и не вводи данные ради бонуса. {url}",
    ),
    (
        0,
        "news",
        "ru",
        "game",
        1,
        "Редакция сообщает о проверке рекламы. В новости цитируется лозунг «Играй в казино и получай бонус». {url}",
    ),
    (
        0,
        "news",
        "kk",
        "game",
        1,
        "Жаңалық: жарнаманың таралуы зерттеліп жатыр. Журналист «қосыл да бонус ал» деген мәтінді мысалға келтірді. {url}",
    ),
    (
        0,
        "news",
        "mixed",
        "game",
        1,
        "Репортаж о сетевых объявлениях. Редакция приводит скриншот «тіркел, казино бонус береді» для обсуждения. {url}",
    ),
    (
        0,
        "news",
        "ru",
        "shop",
        1,
        "Новость городского портала: магазин спортивной одежды запустил программу бонусов. Адрес каталога: {url}",
    ),
    (
        0,
        "news",
        "kk",
        "shop",
        1,
        "Редакция хабарлайды: жастар орталығында жаңа кітап көрмесі өтеді. Қатысу шарттары осы бетте. {url}",
    ),
    (
        0,
        "news",
        "ru",
        "game",
        0,
        "Корреспондент изучил историю казино в кинематографе. В статье есть цитата «играй и выигрывай», но нет приглашения участвовать.",
    ),
    (
        0,
        "education",
        "ru",
        "game",
        1,
        "Практикум медиаграмотности: разберите предложение «Регистрируйся в казино, бонус гарантирован». Это учебный пример рекламы. {url}",
    ),
    (
        0,
        "education",
        "kk",
        "game",
        1,
        "Медиасауат сабағында «слот ойна, бонус ал» мәтінін талдаймыз. Бұл жарнама емес, оқу тапсырмасы. {url}",
    ),
    (
        0,
        "education",
        "mixed",
        "game",
        0,
        "Урок для модераторов: сөздің мәнін тексер. Фраза «қосыл, казиноға тіркел» приведена как учебный образец.",
    ),
    (
        0,
        "education",
        "ru",
        "game",
        0,
        "На занятии по вероятности рассматривается рулетка. Не играйте на деньги: посчитайте математическое ожидание на бумаге.",
    ),
    (
        0,
        "education",
        "kk",
        "shop",
        1,
        "Сабаққа арналған сөздік: ә, ғ, қ, ң, ө, ұ, ү, һ, і. Кітаптың қосымша материалдары осында. {url}",
    ),
    (
        0,
        "education",
        "ru",
        "game",
        0,
        "Обучение фактчекингу: сравните цитаты «Но заходи в казино» и «Но забирай бонус». Обе нужны для разбора манипуляций.",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        1,
        "Забирай бонус за первый заказ канцелярии. Регистрируйся в книжном магазине, каталог здесь. {url}",
    ),
    (
        0,
        "ordinary",
        "kk",
        "shop",
        1,
        "Кітап дүкенінің жаңа клубына қосыл. Алғашқы тапсырысқа сыйлық беріледі, мекенжай карточкада. {url}",
    ),
    (
        0,
        "ordinary",
        "mixed",
        "shop",
        1,
        "Жаңа курткаға жеңілдік! Переходи в каталог одежды, получай бонус за покупку. {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        0,
        "Открой депозит в учебном банковском приложении. Бонус за знакомство с финансовой грамотностью, без настоящих переводов.",
    ),
    (
        0,
        "ordinary",
        "kk",
        "shop",
        0,
        "Банк депозиті туралы ақпараттық кездесу. Тіркеліңіз, қатысушыларға тегін дәптер беріледі.",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        0,
        "Новый ноутбук: два слота оперативной памяти и быстрый накопитель. Заходи в магазин, бонус по карте покупателя.",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        0,
        "Киноклуб показывает фильм «Казино». Регистрируйся на бесплатное обсуждение, места ограничены.",
    ),
    (
        0,
        "ordinary",
        "mixed",
        "shop",
        0,
        "Көрмеге келіңіз! Выставка игровых автоматов прошлого века, музейный билет дает бонус в кафе.",
    ),
    (
        0,
        "ordinary",
        "kk",
        "shop",
        1,
        "Тіл үйрену орталығының тобына қосыл. Сабақ кестесі мен тегін танысу сабағы осы бетте. {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        "shop",
        1,
        "Приглашаем на шахматный турнир библиотеки. Регистрация бесплатная, бонус — закладка для книги. {url}",
    ),
    (
        0,
        "free_game",
        "ru",
        "free",
        1,
        "Играй в бесплатный симулятор рулетки на уроке. Учебные жетоны не покупаются и не выводятся. {url}",
    ),
    (
        0,
        "free_game",
        "kk",
        "free",
        1,
        "Тегін ойынға қосыл: бұл ықтималдықты үйренуге арналған жаттығу, ақша мен ұтыс жоқ. {url}",
    ),
    (
        0,
        "free_game",
        "mixed",
        "free",
        0,
        "Учебная рулетка без ставок: тіркелудің қажеті жоқ. Бесплатная игра использует только жетоны занятия.",
    ),
    (
        0,
        "free_game",
        "ru",
        "free",
        0,
        "Бесплатная игра в музее предлагает крутить колесо истории. Денежных ставок и вывода нет; бонусом станет открытка.",
    ),
    (
        0,
        "ambiguous",
        "ru",
        "missing",
        1,
        "В архиве осталась одна ссылка без подписи. Содержимое и назначение не установлены. {url}",
    ),
    (
        0,
        "ambiguous",
        "kk",
        "missing",
        1,
        "Кім жібергені белгісіз бос хабарлама. Бет ашылмайды, қосымша материал жоқ. {url}",
    ),
    (
        0,
        "ambiguous",
        "mixed",
        "missing",
        1,
        "Ескі мекенжай табылды. Приглашения и призывов в сохраненном тексте нет. {url}",
    ),
    (
        0,
        "ambiguous",
        "ru",
        "missing",
        1,
        "Заметка исследователя содержит недоступный адрес и дату. Другие сведения не сохранились. {url}",
    ),
]


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def normalized(text):
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+|\b[A-Z0-9]{6,}\b|DEMO\.", " ", text)).casefold().strip()


def build():
    freeze = ROOT / "reports/versions/synthetic-v2/core-freeze.json"
    if not freeze.exists() or (OUT / "test.jsonl").exists():
        raise RuntimeError("Core must be frozen first; existing final inputs must never be overwritten.")
    assert len(CASES) == 80 and sum(row[0] for row in CASES) == 40
    inputs, labels, pages = [], [], {}
    for i, (truth, category, language, destination, hops, template) in enumerate(CASES):
        token = digest("final-after-core-freeze-v2-" + str(i))
        host = "https://t" + digest(token + "domain")[:10] + ".test"
        code = "F" + digest(token + "campaign")[:7].upper()
        terminal = host + "/room/" + digest(token + "room")[:6] + "?ref=" + code
        url = host + "/entry/" + digest(token + "entry")[:6] if hops else terminal
        text = "DEMO. " + template.format(code=code, url=url)
        if destination != "missing":
            content = {
                "game": f"<h1>DEMO · зал {token[:5]}</h1><p>Каталог развлечений: казино, рулетка и слоты. Бонус на первый игровой вечер. Денежные операции здесь не реализованы.</p>",
                "shop": f"<h1>DEMO · центр {token[:5]}</h1><p>Книжный клуб, одежда, учебные курсы. Программа подарков постоянным посетителям. Обычная торговля без денежных игр.</p>",
                "free": f"<h1>DEMO · практикум {token[:5]}</h1><p>Бесплатный симулятор. Учебная рулетка без ставок, деньги не используются. Жетоны занятия не имеют стоимости.</p>",
            }[destination]
            pages[terminal] = {"status": 200, "body": content}
            chain = (
                [url] + [host + "/move/" + digest(token + str(j))[:6] for j in range(hops - 1)] + [terminal]
            )
            for j, (source, target) in enumerate(zip(chain, chain[1:])) if hops else []:
                pages[source] = (
                    {"status": 307 if j % 3 == 0 else 302, "headers": {"location": target}}
                    if j % 2 == 0
                    else {
                        "status": 200,
                        "body": '<p>DEMO. Информация участнику.</p><a href="'
                        + target
                        + '">Следующая карточка</a>',
                    }
                )
        is_image = i % 5 in (1, 3)
        qr = i in (8, 23, 48, 63)
        image_name = None
        ocr_reference = text.replace(url, "QR") if qr else text
        rotation = 90 if i in (6, 26, 46, 66) else 180 if i in (13, 33, 53, 73) else 0
        small = i in (18, 38, 58, 78)
        if is_image:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20 if small else 29)
            lines = textwrap.wrap(ocr_reference, width=78 if small else 61, break_long_words=False)
            image = Image.new("RGB", (1180, 90 + len(lines) * 48 + (400 if qr else 0)), "#fffdf8")
            draw = ImageDraw.Draw(image)
            for line_index, line in enumerate(lines):
                draw.text((35, 30 + line_index * 48), line, font=font, fill="#26334a")
            if qr:
                matrix = cv2.QRCodeEncoder_create().encode(url)
                matrix = cv2.copyMakeBorder(matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
                matrix = np.repeat(np.repeat(matrix, 8, axis=0), 8, axis=1)
                image.paste(Image.fromarray(matrix).convert("RGB"), (35, 60 + len(lines) * 48))
            image = image.rotate(rotation, expand=True)
            image_name = "images/" + digest(token + "image") + ".jpg"
            image.save(OUT / image_name, quality=42 if small else 88)
        inputs.append(
            {
                "id": token,
                "materials": [
                    {
                        "text": "" if is_image else text,
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
                "split": "test",
                "truth": truth,
                "category": category,
                "language": language,
                "image": is_image,
                "qr": qr,
                "rotation": rotation,
                "small_compressed": small,
                "family": "final-authored-" + digest(template),
                "campaign": code,
                "domains": [host],
                "reference_text": text,
                "ocr_reference": ocr_reference,
                "expected_destination": terminal if destination != "missing" else None,
                "annotation_provenance": "Author-created synthetic label after core freeze; no independent expert adjudication.",
                "label_note": "Authored hidden promotion with intentionally unavailable destination; evidence can be insufficient."
                if truth and destination == "missing"
                else "No promotional intent in the authored available source."
                if not truth
                else "Authored invitation promoting the synthetic gaming destination.",
            }
        )
    prior = [
        json.loads(line)
        for file in (ROOT / "datasets/synthetic-v1/annotations.jsonl", OUT / "dev-annotations.jsonl")
        for line in file.read_text(encoding="utf-8").splitlines()
    ]
    old_domains = {
        urlsplit(url).hostname
        for row in prior
        for url in re.findall(
            r"https?://[^\s]+", row["reference_text"] + " " + (row.get("expected_destination") or "")
        )
    }
    old_domains.update(urlsplit(url).hostname for row in prior for url in row.get("domains", []))
    new_domains = {urlsplit(url).hostname for row in labels for url in row["domains"]}
    assert not new_domains & old_domains
    assert not {row["family"] for row in labels} & {row["family"] for row in prior}
    assert len({normalized(row["reference_text"]) for row in labels}) == 80
    similarities = []
    for row in labels:
        match = max(
            prior,
            key=lambda old: SequenceMatcher(
                None, normalized(row["reference_text"]), normalized(old["reference_text"])
            ).ratio(),
        )
        similarities.append(
            {
                "id": row["id"],
                "closest_prior": match["id"],
                "ratio": round(
                    SequenceMatcher(
                        None, normalized(row["reference_text"]), normalized(match["reference_text"])
                    ).ratio(),
                    4,
                ),
            }
        )
    audit = {
        "cases": 80,
        "positives": 40,
        "negatives": 40,
        "images": sum(r["image"] for r in labels),
        "qr": sum(r["qr"] for r in labels),
        "core_freeze_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(),
        "overlap_domains": [],
        "overlap_families": [],
        "new_campaigns": len({r["campaign"] for r in labels}),
        "exact_normalized_source_duplicates": 0,
        "closest_source_pairs": sorted(similarities, key=lambda r: r["ratio"], reverse=True),
        "qualification": "String/template and domain separation do not establish independent authorship or semantic independence. Topic classes deliberately recur.",
    }
    for name, rows in (("test.jsonl", inputs), ("test-annotations.jsonl", labels)):
        (OUT / name).write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
        )
    (OUT / "test-pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "separation-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in audit.items() if key != "closest_source_pairs"}, ensure_ascii=False
        )
    )
    print("Closest prior sources:", audit["closest_source_pairs"][:5])


if __name__ == "__main__":
    build()
