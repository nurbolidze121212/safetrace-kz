"""New authored final inputs, created only after the v3 analysis core was frozen."""

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
OUT = ROOT / "datasets/synthetic-v3"

# truth, scenario, language, destination fixture, route steps, independently authored source
CASES = [
    (
        1,
        "direct",
        "ru",
        None,
        0,
        "Вечерний стол открыт: играй в казино на деньги, активируй бонус по коду {code}.",
    ),
    (
        1,
        "direct",
        "kk",
        "game",
        1,
        "Бүгінгі кешке ұсыныс: казиноға тіркел, алғашқы ұтысқа сыйлық ал. Жеке кодың {code}. {url}",
    ),
    (
        1,
        "direct",
        "mixed",
        "game",
        0,
        "Кешкі жоспар дайын: играй в денежную рулетку, забирай фриспины. Кіру: {url}",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        2,
        "Для участников вечернего клуба приготовили приветственный подарок. Жми на приглашение и забирай бонус: {url}",
    ),
    (1, "translit", "other", "game", 1, "Kazino keshine qosyl, bonus seni kutip tur. Tirkel: {url}"),
    (
        1,
        "direct",
        "ru",
        None,
        0,
        "Играй в слоты с денежными ставками. Новому участнику доступен промокод {code}.",
    ),
    (
        1,
        "hidden",
        "kk",
        "game",
        1,
        "Арнайы ұсыныс ашылды. Сілтемеге өтіңіз, сыйлық алыңыз, жеке бетте барлық шарт бар: {url}",
    ),
    (
        1,
        "hidden",
        "mixed",
        "game",
        2,
        "Біздің кешкі қауымдастыққа қосыл. Забирай персональный бонус через карточку приглашения: {url}",
    ),
    (
        1,
        "multihop",
        "ru",
        "game",
        3,
        "Два шага до персонального предложения. Переходи через страницу клуба и активируй бонус: {url}",
    ),
    (
        1,
        "contradictory",
        "ru",
        "game_disclaimer",
        1,
        "Клуб подготовил новые условия. Регистрируйся по приглашению, бонус указан внутри: {url}",
    ),
    (
        1,
        "direct",
        "kk",
        None,
        0,
        "Казиноға тіркел, ұтыс үшін ойна, жаңа ойыншыға сыйлық ал. Құпия код — {code}.",
    ),
    (1, "translit", "other", "game", 0, "Perehodi v nash kazino, zabirai bonus dlya pervogo vechera. {url}"),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "Подарок новым подписчикам доступен в закрытом разделе. Заходи по ссылке и забирай свой бонус: {url}",
    ),
    (
        1,
        "multihop",
        "kk",
        "game",
        3,
        "Кешкі клубқа қосыл, жаңа бөлімге өтіңіз, тіркел де сыйлық ал. Бағыт: {url}",
    ),
    (
        1,
        "contradictory",
        "mixed",
        "game",
        1,
        "Алаяқтар көп, сақ болыңыз, бірақ біздің казиноға тіркеліп, бонус ал. Жеке ұсыныс: {url}",
    ),
    (
        1,
        "direct",
        "ru",
        None,
        0,
        "Пополняй игровой счет казино, выбирай рулетку и забирай бонус для следующей ставки.",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        2,
        "Персональная карточка готова. Переходи, подарок участнику появится после регистрации: {url}",
    ),
    (
        1,
        "hidden",
        "kk",
        "game",
        0,
        "Жаңа қатысушыларға шақыру дайын. Өтіңіз, тіркеліңіз, сыйлық алыңыз. Барлық ақпарат осы бетте: {url}",
    ),
    (
        1,
        "multihop",
        "mixed",
        "game",
        3,
        "Бүгін жаңа бөлім бар: заходи через страницу навигации, забирай бонус в последней карточке. {url}",
    ),
    (
        1,
        "translit",
        "other",
        "game",
        1,
        "Vecher v klube: zaregaysya po priglasheniyu, bonus otkroetsya v kabinete. {url}",
    ),
    (
        1,
        "direct",
        "ru",
        None,
        0,
        "Новая серия розыгрышей казино: жми, делай денежные ставки и забирай фриспины по коду {code}.",
    ),
    (
        1,
        "contradictory",
        "ru",
        "game",
        0,
        "Бесплатная игра закончилась, но теперь играй в нашем казино на деньги. Бонус по приглашению: {url}",
    ),
    (
        1,
        "hidden",
        "mixed",
        "game_news",
        1,
        "Қатысушыларға жаңарту: переходи к новым условиям и активируй бонус для своего аккаунта. {url}",
    ),
    (
        1,
        "multihop",
        "ru",
        "game",
        3,
        "Сначала карточка участника, затем персональный кабинет. Жми и забирай бонус на конечной странице. {url}",
    ),
    (
        1,
        "hidden",
        "kk",
        "game",
        2,
        "Кешкі мүмкіндік ашық. Қосыл, өз ұсынысыңды ал, сілтемеде келесі бетке өт: {url}",
    ),
    (
        1,
        "direct",
        "mixed",
        None,
        0,
        "Жаңа ойыншыларға: играй в казино, тіркел және денежный бонус ал. Қатысу коды {code}.",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        0,
        "Вечерняя подборка доступна подписчикам. Заходи по приглашению, предложение действует сегодня. {url}",
    ),
    (
        1,
        "translit",
        "other",
        "game",
        2,
        "Zaletaem segodnya, registriruysya i zabirai podarok v lichnom profile. {url}",
    ),
    (
        1,
        "multihop",
        "ru",
        "game",
        3,
        "Переходи к карточке, затем в раздел для новых гостей. Забирай бонус после последнего перехода: {url}",
    ),
    (
        1,
        "contradictory",
        "kk",
        "game",
        1,
        "Сабақ аяқталды. Енді казиноға тіркел, ұтыс үшін ойна, сыйлық ал! {url}",
    ),
    (
        1,
        "hidden",
        "ru",
        "game",
        1,
        "Заходи в раздел клуба: предложение для новых участников уже открыто. Личный код {code}. {url}",
    ),
    (
        1,
        "hidden",
        "mixed",
        "game",
        2,
        "Қош келдің! Жми на приглашение, забирай персональный подарок, шарттары соңғы бетте. {url}",
    ),
    (
        1,
        "direct",
        "ru",
        "game",
        0,
        "Переходи в казино на вечерний турнир, но осторожно: возможны проигрыши. {url}",
    ),
    (
        1,
        "multihop",
        "kk",
        "game",
        3,
        "Ұсынысқа өтіңіз, келесі карточкаға қосыл, жаңа қатысушыға сыйлық ал. {url}",
    ),
    (
        1,
        "direct",
        "ru",
        "game",
        1,
        "Ночной зал приглашает: жми, играй в казино и активируй приветственные фриспины. {url}",
    ),
    (
        1,
        "direct",
        "mixed",
        None,
        0,
        "Casino club бүгін ашық. Play now, бонус для первого денежного раунда по коду {code}.",
    ),
    (
        1,
        "unresolved",
        "ru",
        "missing",
        1,
        "Новые условия доступны только по личному приглашению. Переходи и забирай бонус: {url}",
    ),
    (1, "unresolved", "kk", "missing", 0, "Жеке ұсыныс дайын. Өтіңіз, жаңа қатысушыға сыйлық алыңыз. {url}"),
    (
        1,
        "unresolved",
        "mixed",
        "missing",
        2,
        "Кешкі шақыру: заходи по ссылке и активируй бонус, подробности в закрытом разделе. {url}",
    ),
    (
        1,
        "unresolved",
        "ru",
        "missing",
        1,
        "Для подписчиков открыли специальный кабинет. Регистрируйся и забирай подарок: {url}",
    ),
    (
        0,
        "warning",
        "ru",
        None,
        0,
        "Осторожно: обещание «играй в казино и забирай бонус» используется в обманных сообщениях. Не переводите деньги.",
    ),
    (
        0,
        "warning",
        "kk",
        "warning",
        1,
        "Сақ болыңыз: «казиноға тіркел, сыйлық ал» деген хабарламаға сенбеңіз. Қауіп туралы ескерту: {url}",
    ),
    (
        0,
        "warning",
        "mixed",
        "warning",
        2,
        "Казино қауіпті, но переходи к памятке о защите семьи. В ней объясняются риски, а не условия игры. {url}",
    ),
    (
        0,
        "warning",
        "ru",
        "warning",
        1,
        "Переходи к карточке для подписчиков и забирай бонусный памятный материал по защите от обмана. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "warning",
        0,
        "Алаяқтар ақша сұрайды. Казиноға өтпеңіз, белгісіз шотқа ақша жібермеңіз. Мына бетте ескерту бар: {url}",
    ),
    (
        0,
        "warning",
        "ru",
        None,
        0,
        "Казино опасно: не играй ради обещанного выигрыша, не активируй сомнительный промокод. Осторожно с рекламой.",
    ),
    (
        0,
        "warning",
        "ru",
        "warning",
        2,
        "Осторожно, в рассылке пишут «Но переходи в казино, бонус готов». Это пример обмана. Разбор: {url}",
    ),
    (
        0,
        "warning",
        "mixed",
        "warning",
        1,
        "Сақ бол: реклама слотов обещает доход. Не пополняй счет и не забирай этот бонус. Памятка: {url}",
    ),
    (
        0,
        "warning",
        "ru",
        "warning",
        0,
        "Казино обещает быстрый выигрыш, но заходи к нам только за памяткой о рисках. {url}",
    ),
    (
        0,
        "warning",
        "kk",
        "warning",
        1,
        "Құмар ойын қауіпті, бірақ сабаққа тіркел, алаяқтықтан қорғануды үйрен. {url}",
    ),
    (
        0,
        "news",
        "ru",
        None,
        0,
        "Корреспондент исследует рекламу казино. Фраза «Жми и забирай фриспины» приведена как цитата из объявления.",
    ),
    (
        0,
        "news",
        "kk",
        "news",
        2,
        "Жаңалық: редакция казино жарнамасын зерттеді. «Тіркел, бонус ал» деген сөздер мақалада келтірілген. {url}",
    ),
    (
        0,
        "news",
        "ru",
        "news",
        1,
        "Новость о рынке казино, однако переходи на страницу расследования редакции. {url}",
    ),
    (
        0,
        "news",
        "mixed",
        "news",
        2,
        "Жаңа материал дайын: заходи к статье, забирай подборку ссылок редакции. {url}",
    ),
    (
        0,
        "news",
        "ru",
        "news",
        0,
        "Журналист выясняет, как распространяются обещания выигрыша. В публикации цитируют «играй в слоты». {url}",
    ),
    (
        0,
        "news",
        "mixed",
        None,
        0,
        "Редакция хабарлайды: в рекламе написано «Казиноға тіркел, bonus ал». Авторы новости анализируют жалобы.",
    ),
    (
        0,
        "education",
        "ru",
        "education",
        1,
        "Учебный разбор: фраза «переходи в казино» — пример рекламного призыва. Забирай конспект урока: {url}",
    ),
    (
        0,
        "education",
        "kk",
        "education",
        2,
        "Медиасауат сабағы: «Казиноға тіркел, сыйлық ал» — жарнама мысалы. Сабаққа өтіңіз: {url}",
    ),
    (
        0,
        "education",
        "ru",
        "education",
        1,
        "Переходи в новый раздел курса, забирай бонусный учебный материал для занятия. {url}",
    ),
    (
        0,
        "education",
        "mixed",
        "education",
        0,
        "Учебный пример закончился, но регистрируйся только на сабақ по медиаграмотности. В примере было слово «казино». {url}",
    ),
    (
        0,
        "education",
        "ru",
        None,
        0,
        "На уроке разбираем схему: «играй в рулетку, гарантированный доход». Это цитата для критического анализа.",
    ),
    (
        0,
        "education",
        "kk",
        "education",
        2,
        "Оқу мысалы: «Казиноға тіркел» деген жарнама қалай әсер етеді? Түсіндіреміз, сабаққа қосыл: {url}",
    ),
    (
        0,
        "free_game",
        "ru",
        "free",
        1,
        "Бесплатная игра без денежных ставок: заходи в виртуальное казино, жетоны нельзя обменять или вывести. {url}",
    ),
    (
        0,
        "free_game",
        "kk",
        "free",
        2,
        "Тегін ойын клубы: казино көрінісі, ақшасыз ойна, виртуалды сыйлық ал. {url}",
    ),
    (
        0,
        "free_game",
        "mixed",
        "free",
        0,
        "Переходи в симулятор: рулетка для урока вероятности, ақшасыз, без вывода денег. {url}",
    ),
    (
        0,
        "free_game",
        "ru",
        None,
        0,
        "Бесплатная игра завершена, но заходи еще раз в виртуальное казино без денежных ставок. Бонус — рисунок персонажа.",
    ),
    (
        0,
        "free_game",
        "ru",
        "free",
        2,
        "Новый раздел развлечений готов. Регистрируйся и забирай подарок участника: {url}",
    ),
    (
        0,
        "free_game",
        "kk",
        "free",
        1,
        "Тегін ойын: казино, бірақ тіркел де ақшасыз ойна. Ақша шығару қызметі жоқ. {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        "bank",
        1,
        "Банк обновил условия: процентная ставка по вкладу и бонус клиенту. Переходи к расчету: {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        "tools",
        2,
        "Забирай строительную рулетку и бонус к набору инструментов. Измерительная лента в каталоге: {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        None,
        0,
        "Для ремонта компьютера доступны два слота оперативной памяти. Заходи в мастерскую, бонус — чистка корпуса.",
    ),
    (
        0,
        "ordinary",
        "mixed",
        "calendar",
        1,
        "Кеңеске жазыл: свободный слот на консультацию уже открыт. Регистрируйся в календаре: {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        "culture",
        2,
        "Театр приглашает на спектакль «Казино». Переходи к афише, забирай бонус на второй билет. {url}",
    ),
    (
        0,
        "ordinary",
        "kk",
        "shop",
        1,
        "Кітап дүкеніне қосыл, жаңа романға сыйлық ал. Жеке ұсыныс коды {code}. {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        "technical",
        0,
        "Новый ноутбук в каталоге. Жми, забирай бонус на аксессуары, характеристики внутри. {url}",
    ),
    (
        0,
        "ordinary",
        "ru",
        None,
        0,
        "Заходи в настольный клуб: здесь нет казино, слотов и денежных ставок. Бонус участнику — бумажная карта.",
    ),
    (
        0,
        "unresolved",
        "ru",
        "missing",
        1,
        "В сообщении остался адрес закрытого справочника. Содержимое неизвестно, предложения играть в доступном тексте нет. {url}",
    ),
    (
        0,
        "unresolved",
        "kk",
        "missing",
        0,
        "Бұрынғы ақпарат беті қазір ашылмайды. Қолда тек осы сілтеме қалды. {url}",
    ),
    (
        0,
        "unresolved",
        "mixed",
        "missing",
        2,
        "Мұрағат сілтемесі: документ сейчас недоступен. В предоставленном тексте нет приглашения или условий. {url}",
    ),
    (
        0,
        "unresolved",
        "ru",
        "missing",
        1,
        "Старая карточка справочной службы: адрес сохранен для проверки доступности. {url}",
    ),
]

PAGES = {
    "game": "Вечерний игровой зал. Казино, денежные ставки, рулетка и слоты. Регистрируйся, забирай фриспины за первый депозит.",
    "game_disclaimer": "Осторожно: проигрыш возможен. Но играй в нашем казино на деньги и забирай бонус для новой ставки.",
    "game_news": "Новости клуба. Казино открыло вечерний зал. Играй в слоты и активируй фриспины.",
    "warning": "Памятка: осторожно с обещаниями казино. Не играйте ради бонуса и не переводите деньги неизвестным. Переходи к советам по защите семьи.",
    "news": "Новость редакции. Корреспондент разбирает рекламу казино. «Регистрируйся и забирай бонус» — цитата из изученного объявления.",
    "education": "Учебный урок медиаграмотности. Фраза «Играй в казино, фриспины для новичков» приведена для разбора рекламной схемы.",
    "free": "Тегін ойын. Бесплатная игра: виртуальное казино без денежных ставок, ақшасыз. Жетоны не имеют денежной стоимости. Играй в симулятор.",
    "shop": "Каталог книг, подписка на чтение, подарочная закладка. Новые романы и учебные пособия. Сыйлық — кітапқа бетбелгі.",
    "bank": "Условия вклада: процентная ставка банка и бонус за открытие депозита. Калькулятор дохода по вкладу.",
    "tools": "Строительная рулетка: измерительная лента на пять метров, уровень и набор крепежа. Бонус к заказу.",
    "calendar": "Запись на прием. Свободный слот на консультацию в среду. Встреча с преподавателем и регистрация в календаре.",
    "technical": "Ноутбук: два слота памяти, разъемы USB, гарантия. Бонус покупателю — сумка для переноски.",
    "culture": "Афиша театра: спектакль «Казино». Актеры, режиссер и время представления. Билеты на пьесу и абонементы.",
}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def normalized(text):
    return re.sub(r"https?://\S+|\b[A-Z0-9]{6,}\b|\bDEMO\b", "", text).casefold().strip()


def build():
    freeze_path = ROOT / "reports/versions/synthetic-v3/core-freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    for name, expected in freeze["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    if OUT.exists():
        raise RuntimeError("Existing final data must never be overwritten.")
    assert len(CASES) == 80 and sum(c[0] for c in CASES) == 40
    (OUT / "images").mkdir(parents=True)
    inputs, labels, pages = [], [], {}
    for i, (truth, category, language, destination, hops, template) in enumerate(CASES):
        token = digest("final-after-freeze-v3:" + str(i))
        host = "https://n" + digest(token + ":host")[:11] + ".test"
        code = "R" + digest(token + ":campaign")[:7].upper()
        terminal = host + "/item/" + digest(token + ":item")[:7] + "?ref=" + code
        url = host + "/entry/" + digest(token + ":entry")[:7] if hops else terminal
        text = "DEMO. " + template.format(code=code, url=url)
        if destination and destination != "missing":
            pages[terminal] = {"status": 200, "body": "<p>DEMO. " + PAGES[destination] + "</p>"}
            chain = (
                [url] + [host + "/next/" + digest(token + str(j))[:7] for j in range(hops - 1)] + [terminal]
            )
            for j, (origin, target) in enumerate(zip(chain, chain[1:])) if hops else []:
                pages[origin] = (
                    {"status": 302 if j % 3 else 307, "headers": {"location": target}}
                    if j % 2 == 0
                    else {
                        "status": 200,
                        "body": f'<p>DEMO. Карточка участника.</p><a href="{target}">Открыть раздел</a>',
                    }
                )
        is_image = i % 5 in (1, 3)
        qr = i in (3, 13, 23, 33, 43, 53, 63, 73)
        rotation = 90 if i in (6, 26, 46, 66) else 180 if i in (13, 33, 53, 73) else 0
        small = i in (8, 18, 28, 38, 48, 58, 68, 78)
        image_name = None
        ocr_reference = text.replace(url, "QR") if qr else text
        if is_image:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 20 if small else 29)
            lines = textwrap.wrap(ocr_reference, width=79 if small else 62, break_long_words=False)
            picture = Image.new("RGB", (1180, 95 + len(lines) * 48 + (400 if qr else 0)), "#fdfbf5")
            draw = ImageDraw.Draw(picture)
            for j, line in enumerate(lines):
                draw.text((34, 28 + j * 48), line, font=font, fill="#29394b")
            if qr:
                matrix = cv2.QRCodeEncoder_create().encode(url)
                matrix = cv2.copyMakeBorder(matrix, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
                matrix = np.repeat(np.repeat(matrix, 8, axis=0), 8, axis=1)
                picture.paste(Image.fromarray(matrix).convert("RGB"), (34, 65 + len(lines) * 48))
            picture = picture.rotate(rotation, expand=True)
            image_name = "images/" + digest(token + ":pixels") + ".jpg"
            picture.save(OUT / image_name, quality=43 if small else 87)
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
                "family": "v3-source-" + digest(template),
                "page_family": destination,
                "campaign": code,
                "domains": [host] if destination else [],
                "reference_text": text,
                "ocr_reference": ocr_reference,
                "expected_destination": terminal if destination and destination != "missing" else None,
                "annotation_provenance": "Author-created synthetic labels after core freeze; author also developed rules. Not independent expert adjudication.",
                "label_note": "Authored promotion with unavailable destination; source may be insufficient for a decision."
                if truth and destination == "missing"
                else "No promotion in the authored material; informational or ordinary context."
                if not truth
                else "Authored invitation to the synthetic money-game destination or direct game promotion.",
            }
        )
    prior = []
    for path in (
        ROOT / "datasets/synthetic-v1/annotations.jsonl",
        ROOT / "datasets/synthetic-v2/dev-annotations.jsonl",
        ROOT / "datasets/synthetic-v2/test-annotations.jsonl",
    ):
        prior += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    context_inputs = [
        json.loads(line)
        for line in (ROOT / "datasets/context-v3-dev/inputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    prior += [
        {
            "id": row["id"],
            "reference_text": " ".join(m.get("text", "") + " " + m.get("url", "") for m in row["materials"]),
        }
        for row in context_inputs
    ]
    old_domains = {
        urlsplit(url).hostname
        for row in prior
        for url in re.findall(
            r"https?://[^\s]+", row["reference_text"] + " " + (row.get("expected_destination") or "")
        )
    }
    old_domains |= {urlsplit(url).hostname for row in prior for url in row.get("domains", [])}
    new_domains = {urlsplit(url).hostname for row in labels for url in row["domains"]}
    assert not new_domains & old_domains
    assert len({normalized(row["reference_text"]) for row in labels}) == 80
    assert not {normalized(row["reference_text"]) for row in labels} & {
        normalized(row["reference_text"]) for row in prior
    }
    closest = []
    for row in labels:
        match = max(
            prior,
            key=lambda old: SequenceMatcher(
                None, normalized(row["reference_text"]), normalized(old["reference_text"])
            ).ratio(),
        )
        closest.append(
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
        "rotation_90": sum(r["rotation"] == 90 for r in labels),
        "rotation_180": sum(r["rotation"] == 180 for r in labels),
        "small_compressed": sum(r["small_compressed"] for r in labels),
        "core_freeze_sha256": hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "overlap_domains": [],
        "exact_normalized_source_duplicates": 0,
        "closest_source_pairs": sorted(closest, key=lambda row: row["ratio"], reverse=True),
        "qualification": "Source texts newly authored after freeze; shared topic classes and thirteen reused destination templates limit independence. Same author wrote development rules and labels. Domain/string separation is not independent expert validation.",
    }
    for name, rows in (("test.jsonl", inputs), ("test-annotations.jsonl", labels)):
        (OUT / name).write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    for name, value in (("test-pages.json", pages), ("separation-audit.json", audit)):
        (OUT / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    print(json.dumps({k: v for k, v in audit.items() if k != "closest_source_pairs"}, ensure_ascii=False))
    print("Closest prior sources:", audit["closest_source_pairs"][:5])


if __name__ == "__main__":
    build()
