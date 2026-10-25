"""Authored development cases. Families stay entirely in train or validation."""

import hashlib
import html
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "datasets/v5-dev"
TEXTS = {
    "ru": [
        "Играй в казино, регистрируйся и забирай приветственный бонус. {u}",
        "Наш игровой зал ждёт вас: пополняй депозит и играй в слоты на деньги. {u}",
        "Вечерний доступ готов. Переходи по приглашению, забирай подарок в профиле. {u}",
        "Забирай бонус в к@зино, регистрируйся сегодня. {u}",
        "Новость для подписчиков. Но играй в нашем казино, пополняй счёт! {u}",
        "Регистрируйся в kаzиno и забирай фриспины. {u}",
        "Честный конкурс книжного магазина. Участие бесплатно, победитель получит книгу. {u}",
        "Новости: журналист расследовал рекламу казино. Переходи к статье о расследовании. {u}",
        "Осторожно: не играйте в казино, не переводите деньги. {u}",
        "Казино не предлагаем. Это магазин: забирай скидку на мебель. {u}",
        "Запишись на консультацию: свободный слот на приём, бонус новым клиентам. {u}",
        "Купи строительную рулетку. Забирай бонус по карте магазина. {u}",
        "Банк изменил процентную ставку по депозиту. Регистрируйся в приложении банка. {u}",
        "Урок медиаграмотности: «Играй в казино и забирай бонус» — пример опасной рекламы. {u}",
        "Бесплатная игра без ставок и без вывода денег. Казино в названии — только жанр симулятора. {u}",
        "Мы не предлагаем казино или слоты. Регистрируйся на спортивную тренировку. {u}",
    ],
    "kk": [
        "Казиноға тіркел, бонус ал, ақшаға ойнаңыз. {u}",
        "Құмар ойын залы ашылды. Тіркеліңіз, депозит толтырыңыз, сыйлық алыңыз. {u}",
        "Жеке кабинетке шақыру дайын. Қосылыңыз, алғашқы сыйлықты алыңыз. {u}",
        "К@зиноға тіркеліңіз, бонус алыңыз. Бүгін бастайық! {u}",
        "Алаяқтардан сақ болыңыз. Бірақ біздің казиноға тіркел, бонус ал! {u}",
        "К а з и н о: тіркел, ақшалай ұтысқа ойнаңыз. {u}",
        "Кітап дүкенінің тегін байқауы. Ақша төлеу қажет емес, сыйлық — кітап. {u}",
        "Редакция хабарлайды: казино жарнамасы туралы жаңалық жарияланды. {u}",
        "Казиноға тіркелмеңіз! Ақша салмаңыз, құмар ойын ойнамаңыз. {u}",
        "Бұл казино емес. Киім дүкеніне тіркел, жеңілдік ал. {u}",
        "Ал казино туралы жаңалықты журналист зерттеді. Мақалаға өтіңіз. {u}",
        "Бонус — дүкеннің сыйлығы. Құмар ойынға қатыспаңыз, алаяқтан сақтаныңыз. {u}",
        "Құмар ойыннан аулақ болыңыз. Сілтемеге өтпеңіз, ақша жібермеңіз. {u}",
        "Сабақ: «Казиноға тіркел, бонус ал» деген жарнаманы талдаймыз. {u}",
        "Тегін ойын, ақшасыз. Казино симуляторында ақша шығару жоқ. {u}",
        "Казино жоқ. Біздің клубта шахмат сабағына қосылыңыз. {u}",
    ],
    "translit": [
        "Registriruysya v kazino, zabirai bonus i igrai na dengi. {u}",
        "Qumar oiynga tirkel, kazino bonus al, kosyl. {u}",
        "Zabirai podarok v lichnom kabinete, perehodi po priglasheniyu. {u}",
        "Perehodi v k@zino, bonus uzhe dostupen. {u}",
        "Scam v drugih gruppah. No registriruysya v nashem kazino, zabirai bonus. {u}",
        "Zaregaisya v k a z i n o i zabirai bonus. {u}",
        "Knizhnyi konkurs: uchastie besplatno, pokupka ne nuzhna, priz kniga. {u}",
        "Novost redakcii: zakryli kazino, zhurnalist napisal ob etom. {u}",
        "Kazino oinama, qosylmanyz, tirkelme. Scam! {u}",
        "Kazino emes. Bul kiyim dukeni, satyp aluga shagyru. {u}",
        "Bank payyz stavkasyn ozgertti, bul depozit turaly habar. {u}",
        "Bos slot — darigerge jazylu uaqyty, aqshaga oiyn joq. {u}",
        "Scam: ne perehodi v kazino, ne otpravlyai dengi. {u}",
        "Urok mediagramotnosti: reklama kazino kak primer opasnosti. {u}",
        "Tegin oiyn, aqshasyz, kazino simulyatory. Dengi vyvesti nelzya. {u}",
        "Magazin predlagaet bonus za pokupku knigi, konkurs bez vznoса. {u}",
    ],
    "mixed": [
        "Бүгін играй в казино, тіркел и забирай бонус. {u}",
        "Ақшаға слоты: регистрируйся, ұтысқа қатыс, бонус ал. {u}",
        "Жаңа шақыру: переходи в личный кабинет, подарок уже готов. {u}",
        "К@зино ашылды, забирай бонус, тіркеліңіз! {u}",
        "Осторожно с чужими ссылками. Бірақ біздің казиноға регистрируйся! {u}",
        "К а з и н оға тіркел, free spins забирай сегодня. {u}",
        "Кітап дүкені проводит бесплатный конкурс. Взнос жоқ, приз — книга. {u}",
        "Жаңалық: журналист расследует рекламу казино. Мақалаға өтіңіз. {u}",
        "Казиноға тіркелмеңіз, не переводите деньги. Бұл қауіпті. {u}",
        "Бұл казино емес, наш магазин продаёт одежду. Забирай скидку. {u}",
        "Ал казино туралы новость редакция уже опубликовала. {u}",
        "Дүкен предлагает строительную рулетку и бонус за покупку. {u}",
        "Процентная ставка банка төмендеді. Депозит туралы хабар. {u}",
        "Сабақ: «Играй в казино, бонус ал» — учебный пример рекламы. {u}",
        "Тегін ойын, без ставок и без вывода денег. Казино симуляторы. {u}",
        "Біз казино ұсынбаймыз. Регистрируйся на урок шахмат, ақшасыз ойын. {u}",
    ],
}


def main():
    if OUT.exists():
        raise RuntimeError("Development dataset exists; preserve its first version")
    (OUT / "images").mkdir(parents=True)
    font_path = next(p for p in [Path("C:/Windows/Fonts/arial.ttf"),
                                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")] if p.exists())
    inputs, annotations, pages = [], [], {}
    for language, texts in TEXTS.items():
        for family, template in enumerate(texts):
            for variant in range(4):
                key = hashlib.sha256(f"v5-development/{language}/{family}/{variant}".encode()).hexdigest()[:18]
                url = f"https://d{key[:10]}.test/join"
                text = template.format(u=url) + f"\nDEMO · {7 + variant}:30"
                label = int(family < 6)
                page = ("Играй в казино: слоты на деньги, регистрация, депозит, бонус."
                        if label else "Учебная информационная страница. Продажа книги или статья. Денежных игр нет.")
                pages[url] = {"status": 200, "body": "<p>" + html.escape(page) + "</p>"}
                material = {"text": text, "source": "DEMO · авторский dev"}
                is_image = variant == 3
                if is_image:
                    font = ImageFont.truetype(str(font_path), 20 if family % 2 else 26)
                    lines = textwrap.wrap(text, width=48, break_long_words=False)
                    image = Image.new("RGB", (760, 100 + 38 * len(lines)), "#f1f5f9")
                    draw = ImageDraw.Draw(image)
                    for row, line in enumerate(lines):
                        draw.text((26, 28 + row * 38), line, font=font, fill="#10223d")
                    image.save(OUT / "images" / (key + ".jpg"), quality=65)
                    material = {"text": "", "source": "DEMO · авторский dev", "image": "images/" + key + ".jpg"}
                inputs.append({"id": key, "materials": [material]})
                annotations.append({"id": key, "truth": label, "language": language, "image": is_image,
                                    "family": f"dev/{language}/{family}", "split": "validation" if family in {2, 5, 9, 13} else "train",
                                    "reference_text": text, "provenance": "Author-created development label, not independent"})
    for name, rows in [("inputs.jsonl", inputs), ("annotations.jsonl", annotations)]:
        (OUT / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    (OUT / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print(json.dumps({"cases": len(inputs), "images": sum(a["image"] for a in annotations),
                      "validation": sum(a["split"] == "validation" for a in annotations)}))


if __name__ == "__main__":
    main()
