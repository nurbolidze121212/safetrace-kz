"""Script-free, self-contained reading view for the full machine-readable dossier."""

import html
import json

CONTEXTS = {
    "promotion": "Продвижение",
    "warning": "Предупреждение",
    "news": "Новость",
    "education": "Образовательный разбор",
    "free_game": "Бесплатная игра",
    "affiliate": "Партнерское предложение",
    "ambiguous": "Неоднозначно",
}
STATUSES = {
    "pending": "Ожидает",
    "running": "Выполняется",
    "completed": "Завершен",
    "partial": "Частично",
    "error": "Ошибка",
    "cancelled": "Отменен",
}
MODES = {
    "local": "Локальный анализ",
    "cloud": "Облачный контекст",
    "synthetic": "Синтетический стенд",
    "replay": "Сохраненный повтор",
}
DECISIONS = {
    "confirmed": "Подтверждены признаки",
    "false_positive": "Ложное срабатывание",
    "needs_data": "Нужны данные",
}
METHODS = {
    "local_rule": "Локальное правило",
    "cloud_model": "Облачная модель",
    "network": "Сетевое наблюдение",
    "synthetic_transport": "Синтетический транспорт",
    "source_text": "Исходный текст",
    "user_supplied": "Заявлено при импорте",
    "ocr": "OCR",
    "manual_correction": "Уточнение аналитика",
    "qr_decode": "Декодирование QR",
    "source_extraction": "Извлечено из материала",
    "url_parser": "Разбор URL",
    "scoped_exact_match": "Совпадение в области назначения",
}
RELATIONS = {
    "published": "Заявленный источник",
    "contains_link": "Содержит ссылку",
    "redirects": "HTTP-переход",
    "page_link": "HTML-ссылка",
    "contains_identifier": "Содержит идентификатор",
    "matching_identifier": "Совпадение идентификатора",
    "observed": "Наблюдение",
    "on_domain": "Домен адреса",
}


def esc(value):
    return html.escape(str(value) if value is not None else "—", quote=True)


def label(mapping, value):
    return esc(mapping.get(value, value or "Не определено"))


def table(headers, rows):
    return (
        "<div class='table-scroll'><table><thead><tr>"
        + "".join(f"<th scope='col'>{esc(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in rows)
        + "</tbody></table></div>"
    )


def quote_block(text):
    text = str(text or "")
    full = f"<blockquote>{esc(text)}</blockquote>"
    return (
        f"<details><summary>{esc(text[:220])}… · весь фрагмент</summary>{full}</details>"
        if len(text) > 700
        else full
    )


def priority(record):
    if record.get("sufficient_data") is False:
        return "Недостаточно данных"
    score = record.get("score")
    if not score:
        return "Еще не оценен"
    level = {"high": "Высокий", "medium": "Средний", "low": "Низкий"}.get(score.get("level"), "")
    return f"{esc(score.get('value'))} / 100 · {level}"


def render(report):
    materials = report.get("materials", [])
    material_numbers = {m["id"]: i for i, m in enumerate(materials, 1)}
    graph = report.get("graph", {})
    evidence = graph.get("evidence", report.get("evidence", []))
    evidence_numbers = {e["id"]: i for i, e in enumerate(evidence, 1)}
    nodes = {n["id"]: n for n in graph.get("nodes", [])}

    def refs(ids):
        return (
            " ".join(
                f"<a href='#evidence-{evidence_numbers[eid]}'>[{evidence_numbers[eid]}]</a>"
                if eid in evidence_numbers
                else "<span>Источник не найден</span>"
                for eid in dict.fromkeys(ids)
            )
            or "—"
        )

    score = report.get("score") or {}
    winner = material_numbers.get(score.get("material_id"))
    body = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        "<meta name='generator' content='SafeTrace KZ report-2'><title>SafeTrace KZ — досье</title>",
        """<style>
        :root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f2f4f7;color:#20314a;font:15px/1.6 Arial,sans-serif}
        main{max-width:1100px;margin:32px auto;padding:32px 40px;background:white;border:1px solid #dbe1e9;border-radius:12px}
        h1{font-size:29px;line-height:1.25;margin:8px 0 18px}h2{font-size:21px;border-top:1px solid #dbe1e9;padding-top:24px;margin-top:32px}h3{font-size:17px}
        p{margin:10px 0}a{color:#2457a5;text-underline-offset:3px}code,pre{font-family:Consolas,monospace;font-size:12px;overflow-wrap:anywhere}small,.muted{color:#576b83}
        nav{display:flex;flex-wrap:wrap;gap:8px 18px;border-bottom:1px solid #dbe1e9;padding:12px 0 20px}.kicker{text-transform:uppercase;letter-spacing:.13em;font-size:11px;font-weight:bold;color:#576b83}
        .summary{padding:20px 24px;margin:24px 0;background:#f5f8fc;border-left:4px solid #315f9e}.summary h2{border:0;padding:0;margin:0}.priority-value{font-size:24px;font-weight:bold}
        .notice{padding:12px 16px;background:#fff9e8;border:1px solid #e9dfbe}.meta{display:flex;flex-wrap:wrap;gap:6px 24px;color:#576b83;font-size:13px}
        .table-scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;background:#f4f6f9;font-weight:600}th,td{vertical-align:top;padding:10px 12px;border:1px solid #dbe1e9;overflow-wrap:anywhere}
        blockquote{margin:12px 0;padding:12px 16px;border-left:3px solid #a9bad2;background:#f7f9fc;white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap;padding:16px;background:#f4f6f9}
        article{padding:12px 0 20px;border-bottom:1px solid #e1e6ed}article:target,section:target{outline:2px solid #4c74b1;outline-offset:6px}summary{cursor:pointer;color:#345575;padding:8px 0}li{margin:6px 0}
        @media(max-width:700px){main{margin:0;padding:20px;border-radius:0}h1{font-size:23px}th,td{padding:8px}.summary{padding:16px}}
        @media print{body{background:white}main{margin:0;padding:0;border:0;max-width:none}nav,.technical{display:none}a{color:inherit}tr,blockquote{break-inside:avoid}h2,h3{break-after:avoid}}
        </style></head><body><main>""",
        "<header><p class='kicker'>SafeTrace KZ · досье ручной проверки</p>",
        f"<h1>{esc(report.get('title'))}</h1><div class='meta'><span>Случай: <code>{esc(report.get('id'))}</code></span><span>Создан: {esc(report.get('created_at'))}</span></div>",
        f"<p>{label(MODES, report.get('mode'))}. Авторство источников не проверено. Даты сохранены с часовым поясом.</p></header>",
        "<nav aria-label='Разделы досье'><a href='#summary'>Результат</a><a href='#causes'>Основания</a><a href='#materials'>Материалы</a><a href='#routes'>Маршруты</a><a href='#relationships'>Связи</a><a href='#evidence'>Источники</a><a href='#decisions'>Решения</a><a href='#integrity'>Файлы</a></nav>",
    ]
    if report.get("mode") in ("synthetic", "replay"):
        body.append(
            "<p class='notice'>Синтетические материалы и страницы. Сохраненный результат; открытие этого файла не запускает новый анализ.</p>"
        )
    body += [
        "<section class='summary' id='summary'><h2>Результат проверки</h2>",
        f"<p class='priority-value'>{priority(report)}</p><p>Статус обработки: <strong>{label(STATUSES, report.get('status'))}</strong></p>",
        "<p>Индекс определяет приоритет ручной проверки. Это не вероятность нарушения и не юридическое заключение.</p>",
    ]
    if report.get("status") in ("pending", "running") and score:
        body.append("<p class='notice'>Показан предыдущий индекс. Новый анализ еще не завершен.</p>")
    if report.get("analysis_assisted"):
        body.append(
            "<p class='notice'>Анализ с ручным уточнением адреса. Первичный автоматический результат сохранён в истории; это уточнение не включается в автоматические метрики качества.</p>"
        )
    if winner:
        body.append(
            f"<p>Индекс определяется <a href='#material-{winner}'>материалом {winner}: {esc(materials[winner - 1]['source'])}</a>.</p>"
        )
    body.append("</section><section id='causes'><h2>Основания приоритета</h2>")
    if history := report.get("history"):
        body.append(
            "<h3>Предыдущие анализы</h3>"
            + table(
                ["Начало", "Статус", "Индекс / полнота", "Участие аналитика"],
                [
                    (
                        esc(item.get("at")),
                        label(STATUSES, item.get("status")),
                        priority(item),
                        "Ручное уточнение адреса"
                        if item.get("analysis_assisted")
                        else "Автоматический анализ",
                    )
                    for item in history
                ],
            )
        )
        body.append(
            "<p>Полные сохранённые материалы, основания и этапы предыдущих анализов находятся в history файла case.json. Незавершённый индекс не считается нулевым.</p>"
        )
    contributions = score.get("contributions", [])
    body.append(
        table(
            ["Основание", "Вклад", "Цитаты"],
            [
                (esc(c["title"]), esc(f"{c['weight']:+}"), refs(c.get("evidence_ids", [])))
                for c in contributions
            ],
        )
        if contributions
        else "<p>Подтвержденных вкладов пока нет. Отсутствие признаков не гарантирует безопасность.</p>"
    )
    body.append(
        "<h3>Ограничения</h3><ul>"
        + "".join(f"<li>{esc(x)}</li>" for x in report.get("limitations", []))
        + "</ul></section>"
    )
    if coverage := report.get("provider_input"):
        body.append(
            f"<p class='notice'>Облачный ввод: {'полный' if coverage.get('complete') else 'неполный'}. Передано изображений {esc(coverage.get('images_sent'))} из {esc(coverage.get('images_total'))}. Размер JSON данных: {esc(coverage.get('serialized_chars'))} символов. Подробное покрытие сохранено в case.json.</p>"
        )
    body.append("<section id='materials'><h2>Исходные материалы</h2>")
    for i, material in enumerate(materials, 1):
        context = material.get("context") or {}
        body += [
            f"<article id='material-{i}'><h3>Материал {i} · {esc(material.get('source'))}</h3>",
            f"<p><strong>{priority(material)}</strong> · Контекст: {label(CONTEXTS, context.get('context'))}</p>",
            f"<p><a href='originals/{i:02d}-text.txt' download>Скачать оригинал текста (UTF-8)</a> · SHA-256: <code>{esc(material.get('original_sha256', 'не зафиксирован'))}</code></p>",
        ]
        if material.get("image_id"):
            extension = material["image_id"].rsplit(".", 1)[1]
            body.append(
                f"<p><a href='originals/{i:02d}.{esc(extension)}' download>Скачать оригинальное изображение</a> · SHA-256: <code>{esc(material.get('image_sha256', 'не зафиксирован'))}</code></p>"
            )
        if material.get("published_at"):
            body.append(f"<p>Заявленное время публикации: {esc(material['published_at'])}</p>")
        if material.get("text"):
            body.append(quote_block(material["text"]))
        if material.get("url"):
            body.append(f"<p>Исходный URL: <code>{esc(material['url'])}</code></p>")
        if ocr := material.get("ocr"):
            body.append(
                f"<h4>Распознанный текст</h4>{quote_block(ocr.get('text'))}<p class='muted'>Модель: {esc(ocr.get('model'))}. Координаты и оценки строк сохранены в JSON.</p>"
            )
        if material.get("duplicate_of"):
            body.append(
                "<p class='notice'>Содержание совпадает с другим материалом случая; копия не считается независимым подтверждением.</p>"
            )
        if readings := material.get("url_reviews"):
            body.append(
                "<h4>Сверка OCR-адресов</h4>"
                + table(
                    ["Первичное чтение", "Использованный адрес / состояние", "Источники"],
                    [
                        (
                            esc(r["raw_url"]),
                            esc(r.get("selected_url") or "Не открывался: требуется сверка")
                            + ("<br>Уточнение аналитика" if r.get("correction_id") else ""),
                            refs(
                                r.get("source_evidence_ids", [])
                                + ([r["selected_evidence_id"]] if r.get("selected_evidence_id") else [])
                            ),
                        )
                        for r in readings
                    ],
                )
            )
        if corrections := material.get("url_corrections"):
            body.append(
                "<h4>История уточнений адресов</h4>"
                + table(
                    ["Время", "Первичный адрес → уточнение", "Комментарий"],
                    [
                        (
                            esc(c["at"]),
                            esc(c["original_url"]) + " → " + esc(c["corrected_url"]),
                            esc(c["comment"]),
                        )
                        for c in corrections
                    ],
                )
            )
        if bindings := material.get("call_bindings"):
            body.append(
                "<h4>Призыв и конкретная ветвь назначения</h4>"
                + table(
                    ["Призыв", "Адрес / область", "Основания"],
                    [
                        (
                            esc(b["quote"]),
                            esc(b.get("root_url") or "Адрес не определён")
                            + (
                                "<br>Предположение по единственному адресу материала"
                                if b["method"] == "single_material_target"
                                else ""
                            ),
                            refs(
                                [
                                    b["call_evidence_id"],
                                    *b["root_evidence_ids"],
                                    *b["route_evidence_ids"],
                                    *b["destination_evidence_ids"],
                                ]
                            ),
                        )
                        for b in bindings
                    ],
                )
            )
        if codes := material.get("qr", {}).get("codes"):
            body.append(
                "<h4>QR-коды</h4>"
                + table(
                    ["Содержимое", "Обработка", "Источник"],
                    [
                        (
                            f"<code>{esc(c.get('text'))}</code>",
                            esc(c.get("reason") or "HTTP/HTTPS передан в ограниченный обход"),
                            refs([c["evidence_id"]]),
                        )
                        for c in codes
                    ],
                )
            )
        for contradiction in context.get("contradictions", []):
            body.append(f"<p class='notice'>{esc(contradiction)}</p>")
        body.append("</article>")
    body.append(
        "</section><section id='routes'><h2>Проверенные участки маршрутов</h2><p>HTTP-переход и HTML-ссылка — разные наблюдения. Список может содержать несколько ветвей; непроверенный участок не означает безопасное назначение.</p>"
    )
    observations = report.get("trace", {}).get("observations", [])
    if observations:
        for i, observation in enumerate(observations, 1):
            context = observation.get("context") or {}
            body += [
                f"<article><h3>Наблюдение {i} · {esc(observation.get('status_code') or 'нет ответа')}</h3><p><code>{esc(observation.get('url'))}</code></p>",
                f"<p class='meta'>{esc(observation.get('at'))} · {label(METHODS, observation.get('method'))} · {refs([observation['evidence_id']])}</p>",
            ]
            if observation.get("stop"):
                body.append(f"<p class='notice'>Непроверенный участок: {esc(observation['stop'])}</p>")
            if observation.get("text"):
                body.append(quote_block(observation["text"]))
            if context:
                body.append(
                    f"<p>Контекст страницы: <strong>{label(CONTEXTS, context.get('context'))}</strong> · локальное правило</p>"
                )
                body.extend(
                    f"<p class='notice'>{esc(item)}</p>" for item in context.get("contradictions", [])
                )
            body.append("</article>")
    else:
        body.append("<p>Наблюдений переходов нет.</p>")
    relations = report.get("trace", {}).get("relations", [])
    if relations:
        body.append(
            "<h3>Направления переходов</h3>"
            + table(
                ["Откуда", "Тип", "Куда", "Источник"],
                [
                    (
                        f"<code>{esc(r.get('from') or 'Исходный материал')}</code>",
                        label(RELATIONS, r.get("type")),
                        f"<code>{esc(r.get('to'))}</code>",
                        refs([r["evidence_id"]]),
                    )
                    for r in relations
                ],
            )
        )
    if unvisited := report.get("trace", {}).get("unvisited", []):
        body.append(
            f"<p class='notice'>Из-за ограничений обхода осталось непроверенных переходов: {len(unvisited)}. Адреса и причины сохранены в case.json.</p>"
        )
    body.append(
        "</section><section id='relationships'><h2>Связи и их источники</h2><p>Совпадение идентификатора в области домена и пути — основание для проверки, а не доказательство общего владельца. Заявленный источник не подтверждает авторство.</p>"
    )
    body.append(
        table(
            ["Источник → назначение", "Связь", "Статус / метод", "Фрагменты"],
            [
                (
                    esc(nodes.get(e["source"], {}).get("label", e["source"]))
                    + " → "
                    + esc(nodes.get(e["target"], {}).get("label", e["target"])),
                    label(RELATIONS, e.get("type")),
                    ("Наблюдаемая" if e.get("status") == "observed" else "Предполагаемая")
                    + " · "
                    + label(METHODS, e.get("method")),
                    refs(e.get("evidence_ids", [])),
                )
                for e in graph.get("edges", [])
            ],
        )
    )
    body.append(
        "</section><section id='evidence'><h2>Сохраненные источники выводов</h2><p>Номер в квадратных скобках ведет к конкретному фрагменту. Полные идентификаторы, координаты и атрибуты доступны в case.json.</p>"
    )
    for i, item in enumerate(evidence, 1):
        body += [
            f"<article id='evidence-{i}'><h3>[{i}] {label(METHODS, item.get('method'))}</h3>",
            f"<p class='meta'>{esc(item.get('at'))} · <code>{esc(item.get('url') or item.get('source_id'))}</code></p>",
            quote_block(item.get("quote")),
        ]
        if number := material_numbers.get(item.get("material_id")):
            body.append(f"<a href='#material-{number}'>Оригинал материала {number}</a>")
        elif item.get("case_id") and item["case_id"] != report.get("id"):
            body.append(
                f"<p>Связанный случай: <code>{esc(item['case_id'])}</code>. В этом досье сохранен фрагмент; оригиналы другого случая не включены.</p>"
            )
        if item.get("note"):
            body.append(f"<p>{esc(item['note'])}</p>")
        body.append("</article>")
    body.append("</section><section id='decisions'><h2>История ручной проверки</h2>")
    decisions = report.get("decisions", [])
    body.append(
        table(
            ["Когда", "Решение", "Комментарий"],
            [
                (
                    esc(d.get("at")),
                    label(DECISIONS, d.get("decision")),
                    esc(d.get("comment") or "Без комментария"),
                )
                for d in decisions
            ],
        )
        if decisions
        else "<p>Решение аналитика еще не сохранено.</p>"
    )
    body.append(
        "<p>Ручное решение хранится отдельно от автоматического индекса.</p></section><section id='integrity'><h2>Файлы и воспроизводимость</h2><p><a href='case.json'>Полное досье JSON</a> · <a href='manifest.json'>Manifest с размерами и SHA-256</a></p>"
    )
    body.append(
        table(
            ["Компонент", "Версия"],
            [(esc(name), f"<code>{esc(value)}</code>") for name, value in report.get("versions", {}).items()],
        )
    )
    body.append(
        "<p>SHA-256 фиксирует целостность файлов после сохранения. Он не удостоверяет истинность, автора, независимое время или юридическую допустимость.</p>"
    )
    body.append(
        "<details class='technical'><summary>Полные технические данные, включая предыдущие анализы</summary><pre>"
        + esc(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre></details></section></main></body></html>"
    )
    return "\n".join(body).encode("utf-8")
