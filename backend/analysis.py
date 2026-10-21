import json
import re
import unicodedata

from .config import ROOT, RULE_VERSION
from .schemas import Claim, ContextExtraction

WEIGHTS = json.loads((ROOT / "backend" / "weights.json").read_text(encoding="utf-8"))
PATTERNS = {
    "gambling": r"казино(?:ға|да|дан|ның|ны)?|casino|kazino|слот[а-я]*|рулетк[а-я]*|фриспин[а-я]*|free\s*spins?|ставк[а-я]*|джекпот|jackpot|құмар",
    "call_to_action": r"переходи[а-я]*|забира[а-я]*|регистриру[а-я]*|зарегай[а-я]*|пополн[ия][а-я]*|играй(?:те)?|жми(?:те)?|заходи(?:те)?|залетай(?:те)?|активиру[а-я]*|өтіңіз|өтіңдер|өт|тіркел(?!ме)[а-яәіңғүұқөһ]*|қосыл(?!ма)[а-яәіңғүұқөһ]*|ал(?:ыңыз)?|баста(?:ңыз|йық|ңдар)?|perehodi(?:te)?|zabirai(?:te)?|zaregai(?:sya)?|zaregaysya|registriru(?:isya|ysya)|tirkel|kosyl|qosyl|join\s+now|play\s+now",
    "bonus": r"бонус[а-я]*|bonus|промокод[а-я]*|promo\s*code|сыйлы[қғ][а-яәіңғүұқөһ]*|syilyq|siylyq|фриспин[а-я]*|free\s*spins?|кэшбэк",
    "promise": r"выигр[а-я]*|гарантирован[а-я]*\s+доход|заработ[а-я]*|ұты[сз][а-яәіңғүұқөһ]*|ұтып|табыс|легкие деньги|лёгкие деньги|podnim[ai]|x\d+",
    "warning": r"осторожно|мошенни[а-я]*|не переходите|не переводите|не играйте|алаяқ[а-яәіңғүұқөһ]*|өтпеңіз|сақ бол[а-яәіңғүұқөһ]*|қауіпті|скам|scam",
    "news": r"новост[а-я]*|сообщает редакция|корреспондент|журналист[а-я]*|новость|хабарлайды|жаңалық",
    "education": r"учебн[а-я]*|образовательн[а-я]*|разбор схемы|разбираем схему|урок[а-я]*|медиаграмотност[а-я]*|медиасауат[а-яәіңғүұқөһ]*|саба[қғ][а-яәіңғүұқөһ]*|учебный пример|оқу мысалы|түсіндіреміз|памятк[а-яё]*\s+(?:о|об|про)\s+(?:риск[а-яё]*|безопасност[а-яё]*|мошенни[а-яё]*)",
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


ALTERNATIVES = {"warning", "news", "education", "free_game"}


def sentence_span(text, position):
    # OCR line wrapping is not sentence punctuation. Keep original offsets; a
    # blank line still separates paragraphs. Domain dots/query punctuation do
    # not split the sentence containing a URL.
    urls = [
        (m.start(), m.start() + len(m.group().rstrip(".,;:!?)]}»")))
        for m in re.finditer(r"https?://[^\s<>\"«»]+", text, re.I)
    ]
    boundaries = [
        m for m in re.finditer(r"[.!?;]|\n[ \t]*\n", text) if not any(a <= m.start() < b for a, b in urls)
    ]
    start = max((m.end() for m in boundaries if m.end() <= position), default=0)
    end = min((m.start() for m in boundaries if m.start() >= position), default=len(text))
    return start, end


def information_call(text, start, end):
    """Recognize a narrow explicit informational object, not a global whitelist."""
    sentence_start, sentence_end = sentence_span(text, start)
    tail = text[end:sentence_end]
    informational = re.match(
        r"\s*[,—-]?\s*(?:(?:но|бірақ)\s+)?(?:к\s+(?:нам|вам|ним)\s+)?(?:(?:только|лишь|тек)\s+)?"
        r"(?:к|ко|за|на|в)\s+(?:(?:наш[а-яё]*|эт[а-яё]*|нов[а-яё]*|полезн[а-яё]*)\s+){0,2}"
        r"(?:памятк[а-яё]*|расписани[а-яё]*|конспект[а-яё]*|исследовани[а-яё]*|"
        r"стать[а-яё]*|(?:страниц[а-яё]*\s+)?расследовани[а-яё]*)\b",
        tail,
        re.I,
    )
    before = text[sentence_start:start]
    kazakh_object = re.search(r"\b(?:сабаққа|сабаққа\s+ғана|нұсқаулыққа|мақалаға)\s*$", before, re.I)
    return bool(informational or kazakh_object)


def contrast_clause_span(text, position, quoted_spans):
    start, end = sentence_span(text, position)
    clause_start = start
    for match in re.finditer(r"\b(?:но|однако|бірақ|зато)\b", text[start:end], re.I):
        left, right = start + match.start(), start + match.end()
        if any(a <= left < b for a, b in quoted_spans):
            continue
        if left > position:
            end = left
            break
        clause_start = right
    return clause_start, end


def non_gambling_usage(text, match):
    """Narrow lexical exclusions, scoped to the occurrence, never a document blacklist."""
    word = match.group().casefold()
    before, after = text[max(0, match.start() - 100) : match.start()], text[match.end() : match.end() + 100]
    prefix = re.split(r"[.!?;:\n]|\b(?:но|однако|зато|бірақ)\b", before, flags=re.I)[-1]
    negation = re.search(r"\b(?:нет|без|не\s+содержит|не\s+предлагаем)\s+(.*)$", prefix, re.I)
    if negation and re.fullmatch(
        r"(?:(?:онлайн|казино|слот[а-я]*|став[а-я]*|рулетк[а-я]*|выигрыш[а-я]*|и|или)\b|[\s,])*",
        negation.group(1),
        re.I,
    ):
        return True
    if word.startswith("ставк"):
        return bool(
            re.search(
                r"\b(?:процентн[а-я]*|ключев[а-я]*|кредитн[а-я]*|налогов[а-я]*|тарифн[а-я]*)\s+$",
                before,
                re.I,
            )
            or re.match(r"\s+(?:банка|по\s+(?:кредиту|депозиту|вкладу))\b", after, re.I)
        )
    if word.startswith("слот"):
        return bool(
            re.match(
                r"\s+(?:(?:оперативной|для|на)\s+)?(?:памяти|sim|pci|запис[а-я]*|при[её]м[а-я]*|консультац[а-я]*|встреч[а-я]*)\b",
                after,
                re.I,
            )
        )
    if word.startswith("рулетк"):
        return bool(
            re.search(r"\b(?:строительн[а-я]*|измерительн[а-я]*)\s+$", before, re.I)
            or re.match(r"\s*[:—-]?\s*измерительн[а-я]*\s+лент[а-я]*\b", after, re.I)
        )
    return False


def local_context(sources: dict[str, str]) -> ContextExtraction:
    claims = []
    standalone_calls = []
    source_quotes = {}
    for source_id, text in sources.items():
        url_spans = [m.span() for m in re.finditer(r"https?://\S+", text, re.I)]
        quoted_spans = [m.span() for m in re.finditer(r'«[^»]*»|“[^”]*”|"[^"]*"', text)]
        source_quotes[source_id] = quoted_spans
        for kind, pattern in PATTERNS.items():
            accepted = 0
            for match in re.finditer(r"(?<![\w@])(?:" + pattern + r")(?!\w)", text, re.I):
                if any(start <= match.start() < end for start, end in url_spans):
                    continue
                if kind == "gambling":
                    if non_gambling_usage(text, match):
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
                    if information_call(text, match.start(), match.end()):
                        continue
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
    # A contrast word alone does not make an informational call commercial.
    # Require an unquoted game reference in the call's own sentence/contrast clause.
    # Free-game context persists unless there is an explicit transition or money invitation.
    for call in (c for c in claims if c.kind == "call_to_action"):
        if any(start <= call.start < end for start, end in source_quotes[call.source_id]):
            continue
        text = sources[call.source_id]
        start, end = contrast_clause_span(text, call.start, source_quotes[call.source_id])
        sentence_claims = [c for c in claims if c.source_id == call.source_id and start <= c.start < end]
        sentence_kinds = {c.kind for c in sentence_claims}
        game_unquoted = any(
            c.kind == "gambling" and not any(a <= c.start < b for a, b in source_quotes[c.source_id])
            for c in sentence_claims
        )
        has_free_context = any(c.kind == "free_game" for c in claims)
        explicit_transition = re.search(
            r"\b(?:теперь|енді|реальн[а-я]*\s+деньг[а-я]*|на\s+деньги)\b", text[start:end], re.I
        )
        if (
            game_unquoted
            and not sentence_kinds & ALTERNATIVES
            and (not has_free_context or explicit_transition)
        ):
            standalone_calls.append(call.quote)
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
    # These are local scope rules, not a semantic classifier.
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


def score(
    claims,
    page_claims,
    context,
    repeated=False,
    contradictions=None,
    *,
    direct_claims=None,
    destination_calls=None,
    route_evidence_ids=(),
):
    kinds = {c["kind"] for c in claims}
    eligible_pages = [
        c for c in page_claims if c.get("context") not in ALTERNATIVES or c.get("contradictions")
    ]
    alternative_pages = [
        c for c in page_claims if c.get("context") in ALTERNATIVES and not c.get("contradictions")
    ]
    page_kinds = {c["kind"] for c in eligible_pages}
    direct_claims = claims if direct_claims is None else direct_claims
    direct_kinds = {c["kind"] for c in direct_claims}
    direct = {"call_to_action", "gambling"} <= direct_kinds
    selected_calls = (
        [c for c in claims if c["kind"] == "call_to_action"]
        if destination_calls is None
        else destination_calls
    )
    destination = "gambling" in page_kinds and bool(selected_calls)
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
        direct and not destination,
        selected(direct_claims, {"gambling", "call_to_action"}),
    )
    add(
        "destination_and_call",
        "Игровые признаки на странице + призыв",
        destination,
        selected_calls + selected(eligible_pages, {"gambling"}),
    )
    if destination:
        contributions[-1]["evidence_ids"] = list(
            dict.fromkeys(contributions[-1]["evidence_ids"] + list(route_evidence_ids))
        )
    add(
        "destination_alternative_context",
        "Альтернативный контекст страницы: не подтверждает игровой адрес",
        bool(alternative_pages),
        selected(alternative_pages, ALTERNATIVES),
    )
    promotion = direct or destination
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
