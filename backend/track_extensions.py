"""Small auditable extensions for paid draws and investment recruitment.

These indicators do not establish illegality and never change the Track 2 score.
"""

import re

from .analysis import ALTERNATIVES, local_context, sentence_span

VERSION = "track-extensions-1.0"
PATTERNS = {
    "payment": r"взнос\w*|оплат\w*|перев(?:еди|од)\w*\s+на\s+карт\w*|ақша\s+аудар\w*|жарна\w*|төле\w*|zharn[aa]\w*|tole\w*",
    "random_draw": r"розыгрыш\w*|лотере\w*|колес\w*|рандом\w*|жереб\w*|ұтыс\w*|кездейсоқ\w*|uty[sq]\w*|lotere\w*",
    "paid_slot": r"(?:купи|покупка|продажа)\s+(?:номер\w*|слот\w*|билет\w*)|(?:нөмір|билет)\s+сатып\s+ал\w*",
    "investment": r"влож\w*|инвестиру\w*|салым\w*|қаржы\s+сал\w*|ақша\s+сал\w*|qarzhy\s+sal\w*|aqsha\s+sal\w*",
    "return": r"(?:получ\w*|аласың|аласыз|alasy[nz])\s+\d[\d\s]*|удво\w*|екі\s+есе\w*|eki\s+ese|гарантир\w*\s+(?:доход\w*|прибыл\w*)|кепілді\s+(?:табыс|пайда)\w*",
    "urgency": r"остал\w*\s+\d+\s+мест\w*|успей\w*|\d+\s+орын\s+қалды|бүгін\s+ғана|oryn\s+qaldy",
    "recruitment": r"приглас\w*\s+\w*|куратор\w*|жаңа\s+қатысушы\w*|досыңды\s+шақыр\w*|dosyngdy\s+shaqyr\w*",
    "transfer": r"kaspi|каспи|личн\w*\s+карт\w*|жеке\s+карт\w*",
}


def analyze(text, source_id):
    visible = re.sub(r"https?://\S+", lambda m: " " * len(m.group()), text, flags=re.I)
    context = local_context({source_id: text})
    alternative = context.context in ALTERNATIVES and not context.contradictions
    signals = []
    for kind, pattern in PATTERNS.items():
        for match in re.finditer(r"(?<!\w)(?:" + pattern + r")(?!\w)", visible, re.I):
            start, end = sentence_span(visible, match.start())
            prefix = visible[max(start, match.start() - 35):match.start()]
            tail = visible[match.end():min(end, match.end() + 15)]
            if re.search(r"\b(?:не|без|нет|ешқашан)\s*$", prefix, re.I) or re.match(r"\s+(?:емес|жоқ)\b", tail, re.I):
                continue
            signals.append({"kind": kind, "quote": text[match.start():match.end()],
                            "start": match.start(), "end": match.end(), "source_id": source_id})
            break
    kinds = {item["kind"] for item in signals}
    paid = bool(kinds & {"payment", "paid_slot"})
    draw = "random_draw" in kinds
    investment, gain = "investment" in kinds, "return" in kinds
    values = {"track1": 75 if paid and draw else 40 if "paid_slot" in kinds else 0,
              "track3": 75 if investment and gain else 40 if investment and kinds & {"urgency", "recruitment"} else 0}
    if "urgency" in kinds and values["track3"] >= 65:
        values["track3"] += 10
    output = {}
    for track, value in values.items():
        if alternative:
            value = 0
        selected = {"payment", "paid_slot", "random_draw"} if track == "track1" else {"investment", "return", "urgency", "recruitment", "transfer"}
        output[track] = {"version": VERSION, "scope": "extension", "value": value,
                         "level": "high" if value >= 65 else "medium" if value >= 35 else "low",
                         "signals": [s for s in signals if s["kind"] in selected],
                         "alternative_context": context.context if alternative else None,
                         "meaning": "Индекс признаков для ручной проверки; не вывод о незаконности."}
    return output


def from_materials(materials):
    output = {"version": VERSION, "scope": "extension", "materials": []}
    for material in materials:
        # Source and OCR remain separate; signs in unrelated inputs are not combined.
        source_results = [analyze(material.get("text", ""), material["id"]),
                          analyze(material.get("ocr", {}).get("text", ""), material["id"] + "-ocr")]
        output["materials"].append({"material_id": material["id"], **{
            track: max((x[track] for x in source_results), key=lambda r: r["value"]) for track in ("track1", "track3")}})
    return output
