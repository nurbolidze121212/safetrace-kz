"""Author-created final v4 inputs, written only after the final core freeze.

No analyzer/model is imported or called. Labels describe the authored intent and
controlled destination, not model output. This is not independent adjudication.
"""

import hashlib
import html
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/synthetic-v4"

# All wording below was authored after the 2.2.1 core freeze. It is never passed
# to inference as a category, a truth value, a recipe name or an expected URL.
RECIPES = [
    (
        "ru",
        "direct",
        "game",
        "Ночная сессия открывается в десять. Играй в казино, пополняй счёт и получай приветственный бонус: {u}",
    ),
    (
        "kk",
        "direct",
        "game",
        "Кешкі айналым басталды. Казиноға тіркеліңіз, ақша салып ойнаңыз. Жаңа қатысушыға сыйлық бар. {u}",
    ),
    (
        "mixed",
        "direct",
        "game",
        "Бүгін арнайы ұсыныс: активируй промокод и играй в слоты на деньги. Қатысу мекенжайы: {u}",
    ),
    (
        "translit",
        "direct",
        "game",
        "Novyi zal uzhe otkryt. Zaregaisya v kazino, zabirai bonus i nachinai seans: {u}",
    ),
    (
        "ru",
        "direct",
        "game",
        "Не откладывай вечерний раунд: регистрируйся в онлайн-казино. Депозит доступен в личном кабинете {u}",
    ),
    (
        "kk",
        "direct",
        "game",
        "Біздің казино жаңа ойыншыларды күтеді. Тіркеліп, алғашқы ұтысқа қатысыңыз. Толық шарттар: {u}",
    ),
    (
        "mixed",
        "direct",
        "game",
        "Жаңа бөлім жұмыс істейді: заходи в казино и забирай фриспины после пополнения. Мекенжай: {u}",
    ),
    (
        "ru",
        "direct",
        "game",
        "Играй в рулетку за деньги в нашем клубе; бонус начисляется после регистрации. Вход для участников {u}",
    ),
    (
        "ru",
        "hidden",
        "game",
        "Ссылка для тех, кто просил приглашение вчера. Заходите в личный кабинет, подарок уже закреплён: {u}",
    ),
    (
        "kk",
        "hidden",
        "game",
        "Жабық топқа жаңа орындар қосылды. Осы жерден қосылыңыз, алғашқы сыйлықты алыңыз: {u}",
    ),
    (
        "mixed",
        "hidden",
        "game",
        "Кешкі тізім жаңарды. Регистрируйся по карточке участника и забирай бонус до закрытия: {u}",
    ),
    (
        "ru",
        "hidden",
        "game",
        "На странице приглашений появилась ваша карточка. Переходи по адресу, затем забирай бонус в профиле: {u}",
    ),
    (
        "translit",
        "hidden",
        "game",
        "Segodnya priem novyh uchastnikov. Perehodi v lichnyi razdel, bonus uzhe tam: {u}",
    ),
    (
        "kk",
        "hidden",
        "game",
        "Қатысушы билетін осы беттен алыңыз. Тіркелген соң сыйлық беріледі, ұсыныс кешке жабылады: {u}",
    ),
    (
        "mixed",
        "hidden",
        "game",
        "Достар, открылась дополнительная смена. Заходи через персональное приглашение — сыйлық іште: {u}",
    ),
    (
        "ru",
        "hidden",
        "game",
        "Для подписчиков оставили отдельный проход. Жми на приглашение и активируй бонус новичка: {u}",
    ),
    (
        "kk",
        "multihop",
        "chain",
        "Алдымен шақыру парағын ашыңыз. Соңғы батырма арқылы тіркеліп, сыйлық алыңыз: {u}",
    ),
    (
        "ru",
        "multihop",
        "chain",
        "Приглашение проходит через каталог. Переходи в последнюю карточку и регистрируйся как новый участник: {u}",
    ),
    (
        "mixed",
        "multihop",
        "chain",
        "Екі қадам қалды: заходи в навигатор, открой предложение и забирай свой бонус. Бастау: {u}",
    ),
    (
        "translit",
        "multihop",
        "chain",
        "Dlya vhoda nuzhna kartochka iz kataloga. Zaregaisya cherez poslednyuyu ssylku, zabirai bonus: {u}",
    ),
    (
        "ru",
        "multihop",
        "chain",
        "Кнопка участия теперь на второй странице. Регистрируйся через этот переход, подарок будет на конечной площадке: {u}",
    ),
    (
        "mixed",
        "multihop",
        "chain",
        "Қатысушы жолы жаңарды. Переходи к карточке клуба и активируй предложение после навигации: {u}",
    ),
    (
        "kk",
        "multihop",
        "chain",
        "Шақыру картасында тағы бір сілтеме бар. Соған өтіп, клубқа қосылыңыз. Мекенжай төменде: {u}",
    ),
    (
        "ru",
        "multihop",
        "chain",
        "Личный вход спрятан под кнопкой «Продолжить». Заходи через подборку и получай бонус при регистрации: {u}",
    ),
    (
        "ru",
        "contradictory",
        "game",
        "Осторожно с поддельными аккаунтами. Наше отдельное приглашение действует сегодня: регистрируйся и забирай бонус здесь {u}",
    ),
    (
        "kk",
        "contradictory",
        "game",
        "Алаяқ хабарламалардан сақ болыңыз. Біздің өз клубымызға тіркеліңіз, қатысушыға сыйлық дайын: {u}",
    ),
    (
        "mixed",
        "contradictory",
        "game",
        "Учебная часть встречи закончилась. Енді казиноға тіркеліп, ақшаға ойнаңыз; бонус ждёт на странице {u}",
    ),
    (
        "ru",
        "contradictory",
        "game",
        "Днём был бесплатный тренажёр, но вечером играй в казино на реальные деньги. Забирай стартовый бонус: {u}",
    ),
    (
        "kk",
        "contradictory",
        "game",
        "Тегін ойын тек танысу үшін болды, бірақ қазір ақша салып казиноға қосылыңыз. Ұтысқа жол: {u}",
    ),
    (
        "mixed",
        "contradictory",
        "game",
        "Жаңалықта бөтен компания туралы айтылды. А теперь заходи в наш кабинет и активируй бонус: {u}",
    ),
    (
        "ru",
        "multiple_targets",
        "both_game",
        "Доступны два равноправных входа для новых участников. Регистрируйся через {u} или {v}; предложение одинаковое.",
    ),
    (
        "mixed",
        "contradictory",
        "game",
        "Қауіп туралы мақала бөлек жарияланды. Наш клуб принимает новичков: переходи по этому адресу и забирай бонус {u}",
    ),
    (
        "ru",
        "repeated",
        "game",
        "Участникам утренней группы пришло новое приглашение. Заходи за бонусом по персональной ссылке: {u}",
    ),
    (
        "kk",
        "repeated",
        "game",
        "Алғашқы топқа шақыру дайын. Тіркеліп, қатысушы сыйлығын алыңыз. Бастапқы бет: {u}",
    ),
    (
        "mixed",
        "duplicate",
        "game",
        "Кешкі ұсыныс қайта жарияланды. Жми на вход и забирай бонус для нового профиля: {u}",
    ),
    (
        "ru",
        "branched_positive",
        "game",
        "Календарь встреч указан отдельно: {v}. Заходи за новым бонусом через личное приглашение {u}",
    ),
    (
        "mixed",
        "unresolved",
        "missing",
        "Достар, жаңа орын ашылды. Заходи в клуб через приглашение и забирай свой бонус: {u}",
    ),
    (
        "kk",
        "unresolved",
        "missing",
        "Жеке кабинетке тіркеліп, алғашқы сыйлықты алыңыз. Шақыру тек осы мекенжайда: {u}",
    ),
    (
        "translit",
        "unresolved",
        "missing",
        "Ostavili neskolko mest dlya novichkov. Perehodi po lichnomu priglasheniyu, zabirai bonus: {u}",
    ),
    (
        "ru",
        "unresolved",
        "missing",
        "Приём новых участников заканчивается к полуночи. Регистрируйся по приглашению, предложение закреплено за тобой: {u}",
    ),
    (
        "ru",
        "warning",
        "game",
        "Эту рассылку прислал неизвестный. Не регистрируйтесь в казино и не пополняйте счёт по указанному адресу: {u}",
    ),
    (
        "kk",
        "warning",
        "game",
        "Бұл код қауіпті казиноға апарады. Ақша жібермеңіз, сілтемеге өтпеңіз. Алаяқ хабарламаға мысал: {u}",
    ),
    (
        "mixed",
        "warning",
        "game",
        "Сақ болыңыз: в письме требуют депозит и обещают бонус. Не заходите в это казино, адрес оставлен для проверки: {u}",
    ),
    (
        "translit",
        "warning",
        "game",
        "Scam alert: v soobshchenii napisano «zabirai bonus v kazino». Eto tsitata iz rassylki, ne priglashenie: {u}",
    ),
    (
        "ru",
        "warning",
        "game",
        "«Регистрируйся и выигрывай в казино» — приманка из подозрительного сообщения. Не повторяйте эти действия. Источник {u}",
    ),
    (
        "kk",
        "warning",
        "game",
        "Алаяқтар ұтысқа уәде беріп отыр. Казиноға тіркелмеңіз және ақша салмаңыз. Зерттелген мекенжай: {u}",
    ),
    (
        "mixed",
        "warning",
        "game",
        "Қауіпсіздік хабарламасы. Не переходите к депозиту: это чужое казино, а не наш сервис. Проверяемый адрес {u}",
    ),
    (
        "ru",
        "negation",
        "game",
        "Никого не призываем играть или пополнять баланс. Не заходи в казино по адресу из этой жалобы: {u}",
    ),
    (
        "ru",
        "news",
        "game",
        "Корреспондент зафиксировал баннер со словами «Играй в казино, бонус сегодня». Приводим адрес баннера как источник новости: {u}",
    ),
    (
        "kk",
        "news",
        "game",
        "Редакция хабарлайды: жарнамада «казиноға тіркел, сыйлық ал» деген сөздер бар. Бұл шақырудың дәйексөзі ғана. Дерек: {u}",
    ),
    (
        "mixed",
        "news",
        "game",
        "Журналист выяснил, куда ведёт чужая реклама. «Переходи и забирай бонус» — текст рекламодателя, не редакции. Сілтеме: {u}",
    ),
    (
        "ru",
        "news",
        "ordinary",
        "В новости обсуждается схема рекламы. Заходи к расписанию публичного обсуждения {u}. Отдельный QR приложен к архиву источников.",
    ),
    (
        "kk",
        "news",
        "game",
        "Жаңалық: тұрғындар казино жарнамасына шағым түсірді. Мәтінде ешкім тіркелуге шақырмайды. Тексерілген ресурс {u}",
    ),
    (
        "mixed",
        "news",
        "game",
        "Кеше шыққан материалда оператордың мәлімдемесі келтірілген: «Забирай бонус в казино». Цитата нужна для разбора, не для участия. {u}",
    ),
    (
        "ru",
        "news",
        "game",
        "Редакционная заметка описывает закрытый рекламный кабинет казино. Приглашений читателю нет; адрес опубликован как проверяемая ссылка {u}",
    ),
    (
        "translit",
        "news",
        "game",
        "Novost redaktsii: fraza «perehodi v kazino» vzyata iz reklamy. Eto tsitata, a ne sovet chitatelju. Istochnik {u}",
    ),
    (
        "mixed",
        "education",
        "info",
        "Бүгін медиасауат сабағы. Переходи к нашему конспекту исследования: там разобрана реклама казино и обещания выигрыша. {u}",
    ),
    (
        "ru",
        "education",
        "info",
        "Учебная карточка посвящена рискам азартных игр. Заходите за памяткой о безопасности, пример казино разобран внутри: {u}",
    ),
    (
        "kk",
        "education",
        "info",
        "Казино жарнамасын талдау үшін сабаққа тіркеліңіз. Бұл оқу материалы, ақша салу ұсынылмайды. Сабақтың беті {u}",
    ),
    (
        "mixed",
        "education",
        "info",
        "На семинаре разбираем схему бонусных обещаний. Переходи на страницу расследования, ондағы мысал ақша салуға шақырмайды: {u}",
    ),
    (
        "ru",
        "education",
        "info",
        "Казино часто обещает лёгкий выигрыш. Здесь же регистрируйся на образовательный урок по распознаванию таких обещаний: {u}",
    ),
    (
        "kk",
        "education",
        "info",
        "Оқу мысалында казино атауы кездеседі. Сабаққа ғана қосылыңыз, нұсқаулық QR-кодта берілген. {u}",
    ),
    (
        "mixed",
        "education",
        "ordinary",
        "Архивтің уақыты өзгерді. Заходи по адресу расписания {u}. Исторический игровой адрес упомянут отдельно: {v}",
    ),
    (
        "ru",
        "education",
        "info",
        "Преподаватель процитировал «Пополняй счёт, играй в казино», затем объяснил манипуляцию. Материал урока находится здесь: {u}",
    ),
    (
        "ru",
        "free_game",
        "free",
        "Это бесплатная игра с виртуальными фишками, без денежных ставок и без вывода денег. Играй в учебную рулетку: {u}",
    ),
    (
        "kk",
        "free_game",
        "free",
        "Тегін ойын: барлық ұпай виртуалды, ақша төлеу де, ақша алу да жоқ. Ойын бөлмесіне қосылыңыз: {u}",
    ),
    (
        "mixed",
        "free_game",
        "free",
        "Бесплатная игра для друзей. Тіркеліп, виртуалды бонус алыңыз; ақша салуға болмайды. Тренажёр осында {u}",
    ),
    (
        "ru",
        "affiliate",
        "ordinary",
        "Магазин книг начисляет бонус за друга. Регистрируйся по партнёрской ссылке и получай скидку на бумажные издания: {u}",
    ),
    (
        "kk",
        "affiliate",
        "ordinary",
        "Кітапхана серіктестік бағдарламасын ашты. Қосылып, досыңызбен бірге кітапқа жеңілдік алыңыз: {u}",
    ),
    (
        "mixed",
        "affiliate",
        "ordinary",
        "Жаңа велосипедтер келді. Заходи в магазин, промокод даёт скидку на шлем. Партнёрлік бет {u}",
    ),
    (
        "translit",
        "free_game",
        "free",
        "Besplatnaya igra dlya kruzhka, tolko virtualnye fishki. Join now, no money deposits or cash prizes: {u}",
    ),
    (
        "mixed",
        "free_game",
        "free",
        "Тегін ойын бөлмесі осында. Играй бесплатно без денежных ставок: {u}. Код из чужой рекламной подборки приложен отдельно.",
    ),
    (
        "ru",
        "ordinary",
        "ordinary",
        "Для ремонта нужна строительная рулетка. Заходи в каталог инструмента и выбери измерительную ленту: {u}",
    ),
    (
        "kk",
        "ordinary",
        "ordinary",
        "Дәрігерге жазылу уақыты ашылды. Қабылдау кестесіне тіркеліңіз, төлем кассада ғана жасалады: {u}",
    ),
    (
        "mixed",
        "ordinary",
        "ordinary",
        "Банк жариялаған депозит ставкалары өзгерді. Переходи к таблице условий вклада, это банковский продукт: {u}",
    ),
    (
        "ru",
        "ordinary",
        "ordinary",
        "На консультацию освободился слот записи. Регистрируйся на приём в выбранное время через календарь: {u}",
    ),
    (
        "mixed",
        "branched_negative",
        "ordinary",
        "Еріктілерге жаңа ауысым керек. Заходи по адресу записи на смену {u}. Адрес из отдельной жалобы: {v}",
    ),
    (
        "ru",
        "branched_negative",
        "ordinary",
        "Переходи в кабинет городского кружка {u}. В приложении к отчёту приведён ещё один, игровой ресурс: {v}",
    ),
    (
        "kk",
        "negation",
        "ordinary",
        "Біз казино, бәс тігу немесе ақшаға ойын ұсынбаймыз. Бұл тек математика үйірмесі, сабаққа тіркеліңіз: {u}",
    ),
    (
        "mixed",
        "negation",
        "ordinary",
        "Сервис не предлагает казино, слоты или ставки. Біздің сабаққа қосылыңыз: обсуждаем вероятность на обычных задачах. {u}",
    ),
]


def token(index, part, size=12):
    return hashlib.sha256(f"st-kz-v4-final-after-203749-{index}-{part}".encode()).hexdigest()[:size]


def qr_image(value):
    data = cv2.QRCodeEncoder_create().encode(value)
    data = cv2.copyMakeBorder(data, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    return Image.fromarray(np.repeat(np.repeat(data, 7, axis=0), 7, axis=1)).convert("RGB")


def draw_image(index, text, primary, payload):
    size = 28 if index % 10 == 1 else 24 if index % 20 == 0 else 20 if index % 20 == 15 else 26
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", size)
    wrapped = index % 20 == 5
    if wrapped:
        prefix = text.replace(primary, "").strip()
        split = urlsplit(primary)
        domain = f"{split.scheme}://{split.netloc}"
        lines = textwrap.wrap(prefix, width=72, break_long_words=False) + [domain, primary[len(domain) :]]
    else:
        lines = textwrap.wrap(text, width=72 if size >= 24 else 92, break_long_words=False)
    width = max(1120, max(int(font.getlength(line)) for line in lines) + 72)
    qr = qr_image(payload) if payload else None
    line_height = size + 15
    height = 66 + len(lines) * line_height + (qr.height + 35 if qr else 0)
    dark = index % 20 == 6
    image = Image.new("RGB", (width, height), "#182a3b" if dark else "#fbf8ee")
    drawer = ImageDraw.Draw(image)
    for row, line in enumerate(lines):
        drawer.text((30, 25 + row * line_height), line, font=font, fill="#f5f7fa" if dark else "#26384c")
    if qr:
        image.paste(qr, (30, 42 + len(lines) * line_height))
    rotation = 90 if index % 20 == 0 else 0
    if rotation:
        image = image.rotate(rotation, expand=True)
    if index % 20 == 15:
        image = image.filter(ImageFilter.GaussianBlur(0.45))
    suffix = ".jpg" if index % 20 == 10 else ".png"
    filename = token(index, "pixels", 20) + suffix
    image.save(OUT / "images" / filename, quality=45)
    return "images/" + filename, {
        "font_px": size,
        "rotation_ccw": rotation,
        "wrapped_url": wrapped,
        "jpeg_quality": 45 if suffix == ".jpg" else None,
        "dark": dark,
    }


def main():
    freeze = ROOT / "reports/versions/synthetic-v4/core-freeze.json"
    assert freeze.is_file(), "Freeze the final core first"
    assert len(RECIPES) == 80, len(RECIPES)
    assert not OUT.exists(), "Never overwrite final data"
    OUT.mkdir()
    (OUT / "images").mkdir()
    inputs, labels, pages = [], [], {}
    bodies = {
        "game": [
            "<h1>Казино для участников</h1><p>Слоты, рулетка и денежные ставки. Пополнение депозитом.</p>",
            "<h1>Ойын бөлімі</h1><p>Казиноға тіркелу, ақша салу және ұтысты шығару. Слоты қолжетімді.</p>",
            "<h1>Игровой кабинет</h1><p>Онлайн-казино. Депозит для игры на деньги, игровые автоматы и джекпот.</p>",
        ],
        "ordinary": [
            "<h1>Городская запись</h1><p>Календарь встреч, регистрация на консультации и расписание кружков.</p>",
            "<h1>Каталог</h1><p>Книги, инструменты и велосипеды. Обычная скидка на товар по партнёрской ссылке.</p>",
            "<h1>Қызмет кестесі</h1><p>Кітапхана, дәрігер қабылдауы және оқу үйірмесіне жазылу.</p>",
        ],
        "info": [
            "<h1>Учебная памятка</h1><p>Разбор схемы рекламы казино: обещание бонуса не гарантирует выигрыш. Не переводите деньги.</p>",
            "<h1>Медиасауат сабағы</h1><p>Казино жарнамасы қалай жұмыс істейді? Бұл оқу мысалы, ақша салмаңыз.</p>",
        ],
        "free": [
            "<h1>Бесплатная игра</h1><p>Рулетка с виртуальными фишками. Без денежных ставок и без вывода денег.</p>",
            "<h1>Тегін ойын</h1><p>Виртуалды ұпаймен ойын, ақшасыз. Казино емес, тек жаттығу.</p>",
        ],
    }
    for index, (language, category, route, template) in enumerate(RECIPES):
        cid = token(index, "case", 16)
        code = "T" + token(index, "code", 7).upper()
        root = f"https://k{token(index, 'host', 10)}.test/{['invite', 'visit', 'card', 'access'][index % 4]}/{token(index, 'path', 6)}?ref={code}"
        other = f"https://k{token(index, 'second', 10)}.test/{token(index, 'second-path', 7)}"
        if index in (15, 55):
            root = root.replace(root.split("/")[3], "шақыру" if index == 15 else "памятка", 1)
        text = "DEMO. " + template.format(u=root, v=other)
        has_image, has_qr = index % 5 in (0, 1), index % 10 == 1
        qr_only = index in (1, 21, 41, 61)
        payload = (root if qr_only else other) if has_qr else None
        if qr_only:
            text = text.replace(root, "").strip() + " QR төменде."
        material = {"text": text, "url": "", "source": "DEMO · материал " + cid[:6], "image": None}
        style = None
        if has_image:
            material["image"], style = draw_image(index, text, root, payload)
            material["text"] = ""
        materials = [material]
        truth = int(index < 40)
        kind = "game" if route in ("game", "chain", "both_game") else route
        if route == "missing":
            # Intentionally absent destination. The positive authored intent is
            # annotation context; analyzer gets no hidden page or class marker.
            destination = None
        elif route == "chain":
            middle = f"https://k{token(index, 'middle-host', 10)}.test/{token(index, 'middle-path', 7)}"
            destination = f"https://k{token(index, 'target-host', 10)}.test/start?ref={code}"
            pages[root] = {"status": 302, "headers": {"location": middle}}
            pages[middle] = {
                "status": 200,
                "body": f'<h1>Карточка доступа</h1><a href="{html.escape(destination)}">Продолжить</a>',
            }
            pages[destination] = {"status": 200, "body": bodies["game"][index % len(bodies["game"])]}
        else:
            destination = root
            pages[root] = {"status": 200, "body": bodies[kind][index % len(bodies[kind])]}
        if other in text or (has_qr and not qr_only):
            other_kind = (
                "game"
                if route == "both_game" or (not truth and index in (51, 62, 71, 76, 77))
                else "ordinary"
            )
            pages[other] = {"status": 200, "body": bodies[other_kind][index % len(bodies[other_kind])]}
        if category == "repeated":
            materials.append(
                {
                    "text": "DEMO. Кешкі топ енді ашылды, қосылып сыйлық алыңыз. " + root
                    if index == 32
                    else "DEMO. Для второй смены готов новый проход; заходи за бонусом: " + root,
                    "url": "",
                    "source": "DEMO · материал " + token(index, "peer", 6),
                    "image": None,
                }
            )
            language = "mixed"
        elif category == "duplicate":
            materials.append({**material, "source": "DEMO · повторный импорт " + token(index, "peer", 6)})
        expected_materials = []
        for position, m in enumerate(materials):
            visible = [value for value in (root, other) if value in text] if m["image"] else []
            expected_materials.append(
                {"ocr_urls": visible, "qr_payloads": [payload] if m["image"] and payload else []}
            )
        inputs.append({"id": cid, "materials": materials})
        labels.append(
            {
                "id": cid,
                "split": "test",
                "truth": truth,
                "language": language,
                "category": category,
                "image": has_image,
                "qr": has_qr,
                "family": "v4-" + token(index, "family", 14),
                "campaign": code,
                "reference_text": text,
                "ocr_reference": text if has_image else "",
                "materials": expected_materials,
                "expected_destination": destination,
                "image_style": style,
                "annotation_provenance": "Author-created after core freeze; author also developed the rules. No independent human adjudication.",
                "label_note": "Authored invitation to a controlled money-game destination, or an invitation with intentionally unavailable destination known only to the author."
                if truth
                else "Authored warning, quotation, informational/free/ordinary destination or a call directed at an ordinary branch; no invitation to the separate money-game reference.",
            }
        )
    for name, rows in [("inputs.jsonl", inputs), ("annotations.jsonl", labels)]:
        (OUT / name).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )
    (OUT / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "core_freeze_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "n": len(inputs),
        "positive": sum(r["truth"] for r in labels),
        "image_cases": sum(r["image"] for r in labels),
        "qr_cases": sum(r["qr"] for r in labels),
        "purpose": "Fresh author-synthetic final inputs. No predictions computed by the generator. Independent validation unavailable.",
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
