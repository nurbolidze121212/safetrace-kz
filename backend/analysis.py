import json
import re
import unicodedata

from .config import ROOT, RULE_VERSION
from .schemas import Claim, ContextExtraction

WEIGHTS = json.loads((ROOT / "backend" / "weights.json").read_text(encoding="utf-8"))
PATTERNS = {
    "gambling": r"казино|casino|kazino|слот[а-я]*|рулетк[а-я]*|фриспин[а-я]*|free\s*spins?|ставк[а-я]*|джекпот|jackpot|құмар",
    "call_to_action": r"переходи[а-я]*|забира[а-я]*|регистриру[а-я]*|зарегай[а-я]*|пополн[ия][а-я]*|играй(?:те)?|жми(?:те)?|заходи(?:те)?|залетай(?:те)?|активиру[а-я]*|өтіңіз|өтіңдер|өт|тіркел(?!ме)[а-яәіңғүұқөһ]*|қосыл(?!ма)[а-яәіңғүұқөһ]*|ал(?:ыңыз)?|баста(?:ңыз|йық|ңдар)?|perehodi(?:te)?|zabirai(?:te)?|zaregai(?:sya)?|zaregaysya|registriru(?:isya|ysya)|tirkel|kosyl|qosyl|join\s+now|play\s+now",
    "bonus": r"бонус[а-я]*|bonus|промокод[а-я]*|promo\s*code|сыйлы[қғ][а-яәіңғүұқөһ]*|syilyq|siylyq|фриспин[а-я]*|free\s*spins?|кэшбэк",
    "promise": r"выигр[а-я]*|гарантирован[а-я]*\s+доход|заработ[а-я]*|ұты[сз][а-яәіңғүұқөһ]*|ұтып|табыс|легкие деньги|лёгкие деньги|podnim[ai]|x\d+",
    "warning": r"осторожно|мошенни[а-я]*|не переходите|не переводите|не играйте|алаяқ[а-яәіңғүұқөһ]*|өтпеңіз|сақ бол[а-яәіңғүұқөһ]*|қауіпті|скам|scam",
    "news": r"новост[а-я]*|сообщает редакция|корреспондент|журналист[а-я]*|новость|хабарлайды|жаңалық",
    "education": r"учебн[а-я]*|образовательн[а-я]*|разбор схемы|разбираем схему|урок[а-я]*|медиаграмотност[а-я]*|медиасауат[а-яәіңғүұқөһ]*|саба[қғ][а-яәіңғүұқөһ]*|учебный пример|оқу мысалы|түсіндіреміз",
    "free_game": r"без ставок|без денежных|без депозита и|бесплатн[а-я]* игра|тегін ойын|ақшасыз|без вывода денег",
}
EXPLANATIONS = {
    "gambling": "Лексический признак игрового ресурса; сам по себе не доказывает продвижение.",
    "call_to_action": "Возможный рекламный призыв; требуется проверка контекста.",
    "bonus": "Упоминание бонуса или промокода.",
    "promise": "Обещание выигрыша или дохода.",
    "warning": "Альтернатива: предупреждение о вреде или мошенничестве.",
    "news": "Альтернатива: журналистский контекст.",
    "education": "Альтернатива: образовательный разбор.",
    "free_game": "Альтернатива: бесплатная игра без денежных ставок.",
}


def normalize_text(text):
    return unicodedata.normalize("NFKC", text).casefold()


def local_context(sources: dict[str, str]) -> ContextExtraction:
    claims = []
    standalone_calls = []
    for source_id, text in sources.items():
        url_spans = [m.span() for m in re.finditer(r"https?://\S+", text, re.I)]
        quoted_spans = [m.span() for m in re.finditer(r'«[^»]*»|“[^”]*”|"[^"]*"', text)]
        for kind, pattern in PATTERNS.items():
            accepted = 0
            for match in re.finditer(r"(?<![\w@])(?:" + pattern + r")(?!\w)", text, re.I):
                if any(start <= match.start() < end for start, end in url_spans):
                    continue
                if kind == "gambling":
                    if match.group().casefold().startswith("слот") and re.match(
                        r"\s+(?:(?:оперативной|для)\s+)?(?:памяти|sim|pci)\b", text[match.end() :], re.I
                    ):
                        continue
                    if any(start <= match.start() < end for start, end in quoted_spans) and re.search(
                        r"\b(?:спектакл|фильм|роман|пьес|театр|акт[её]р)[а-я]*\b",
                        text[max(0, match.start() - 100) : match.end() + 100],
                        re.I,
                    ):
                        continue
                if kind == "call_to_action":
                    # Keep original offsets; do not turn a negative imperative into a positive one.
                    if re.search(r"\b(?:не|никогда\s+не|ешқашан)\s+$", text[: match.start()], re.I):
                        continue
                    if not any(start <= match.start() < end for start, end in quoted_spans):
                        prefix = re.split(r"[.!?\n]", text[: match.start()])[-1]
                        if re.search(r"\b(?:но|однако|бірақ|зато)\b[^.!?\n]{0,70}$", prefix, re.I):
                            standalone_calls.append(match.group())
                claims.append(
                    Claim(
                        kind=kind,
                        quote=match.group(),
                        source_id=source_id,
                        explanation=EXPLANATIONS[kind],
                        start=match.start(),
                        end=match.end(),
                    )
                )
                accepted += 1
                if accepted == 3:
                    break
    body = "\n".join(sources.values())
    kk = bool(re.search("[әғқңөұүһі]", body, re.I))
    ru = bool(re.search(r"переход|бонус|осторожно|игр|новост", body, re.I))
    kinds = {c.kind for c in claims}
    context = "ambiguous"
    for candidate in ("warning", "news", "education", "free_game"):
        if candidate in kinds:
            context = candidate
            break
    if context == "ambiguous" and "call_to_action" in kinds:
        context = "promotion" if kinds & {"gambling", "bonus", "promise"} else "affiliate"
    # This is deliberately narrow and exposed as a limitation, not a semantic classifier.
    contradictions = []
    if kinds & {"warning", "news", "education", "free_game"} and standalone_calls:
        contradictions.append("Альтернативный контекст соседствует с самостоятельным рекламным призывом.")
    # Preserve at least one claim per source/kind before spending the quote budget on repeats.
    groups = {}
    for claim in claims:
        groups.setdefault((claim.source_id, claim.kind), []).append(claim)
    balanced = [group[index] for index in range(3) for group in groups.values() if index < len(group)]
    return ContextExtraction(
        language="mixed"
        if kk and ru
        else "kk"
        if kk
        else "ru"
        if re.search("[а-я]", body, re.I)
        else "other",
        context=context,
        claims=balanced[:30],
        contradictions=contradictions,
        limitations=["Локальные правила: ограниченное понимание иронии, цитирования, транслита и отрицаний."],
    )


def verify_claims(result: ContextExtraction, sources: dict[str, str]):
    valid, rejected = [], []
    for claim in result.claims:
        text = sources.get(claim.source_id, "")
        start = claim.start if claim.start is not None else text.find(claim.quote)
        end = claim.end if claim.end is not None else start + len(claim.quote)
        if start < 0 or end < start or text[start:end] != claim.quote:
            rejected.append(claim.model_dump())
        else:
            valid.append({**claim.model_dump(), "start": start, "end": end})
    return valid, rejected


def score(claims, page_claims, context, repeated=False, contradictions=None):
    kinds = {c["kind"] for c in claims}
    page_kinds = {c["kind"] for c in page_claims}
    call = "call_to_action" in kinds
    game = "gambling" in kinds
    destination = "gambling" in page_kinds
    contributions = []

    def add(key, title, active, source_claims):
        if active:
            contributions.append(
                {
                    "key": key,
                    "title": title,
                    "weight": WEIGHTS[key],
                    "evidence_ids": list(dict.fromkeys(c["evidence_id"] for c in source_claims)),
                }
            )

    def selected(items, types):
        return [c for c in items if c["kind"] in types]

    add(
        "gambling_and_call",
        "Игровая лексика + призыв",
        game and call and not destination,
        selected(claims, {"gambling", "call_to_action"}),
    )
    add(
        "destination_and_call",
        "Проверенный игровой адрес + призыв",
        destination and call,
        selected(claims, {"call_to_action"}) + selected(page_claims, {"gambling"}),
    )
    promotion = call and (game or destination)
    add(
        "bonus_in_promotion",
        "Бонус в рекламном контексте",
        promotion and "bonus" in kinds,
        selected(claims, {"bonus"}),
    )
    add(
        "promise_in_promotion",
        "Обещание выигрыша",
        promotion and "promise" in kinds,
        selected(claims, {"promise"}),
    )
    add(
        "repeated_referral_in_promotion", "Повтор идентификатора в материалах", promotion and repeated, claims
    )
    alternative = context in ("warning", "news", "education", "free_game")
    add(
        "contradictory_context" if contradictions else "alternative_context",
        ("Самостоятельный призыв при контексте: " if contradictions else "Альтернативный контекст: ")
        + {
            "warning": "предупреждение",
            "news": "новость",
            "education": "образовательный разбор",
            "free_game": "бесплатная игра",
        }.get(context, context),
        alternative,
        selected(claims, {"warning", "news", "education", "free_game"}),
    )
    value = max(0, min(100, sum(c["weight"] for c in contributions)))
    return {
        "value": value,
        "level": "high"
        if value >= WEIGHTS["high_threshold"]
        else "medium"
        if value >= WEIGHTS["medium_threshold"]
        else "low",
        "contributions": contributions,
        "version": RULE_VERSION,
        "weights": WEIGHTS,
        "meaning": "Индекс приоритета ручной проверки, не вероятность нарушения.",
    }
