# Состояние — 21 октября 2026

Ядро SafeTrace KZ и материалы защиты готовы. Этапы A–E проверены; аудит всей SPEC — reports/ACCEPTANCE.md. Проект локальный, публикаций/покупок/удаленного репозитория нет.

- Каталог: C:\Users\nurbo\Desktop\vvv\safetrace-kz; отдельный Git, ветка codex/safetrace-kz. SPEC — неизмененная копия задания. Применимых AGENTS.md не было.
- Windows x64, Python 3.12.14 в .venv, Node 24.13.1. Системный Python 3.14 не используется. CPU проверен; GPU/Linux не проверялись.
- PaddleOCR 3.7.0 / PaddlePaddle 3.3.1, локальные cyrillic_PP-OCRv5_mobile_rec и PP-OCRv5_mobile_det. Первоначальный pip MemoryError обойден совместимой установкой; numpy/PyYAML исправлены, lock и pip check в порядке.
- FastAPI/SQLite, bounded worker/recovery/retry/cancel, оригиналы/OCR/цитаты, локальные правила, Gemini adapter, synthetic/replay, allowlist/IP pinning, граф/evidence, история решений, ZIP.
- Браузер: c1982e9bb36d4448a18b9aa67380a154 создан из нового текста и PNG, дополнен вторым материалом; индекс 80. Решение/комментарий сохранились после reload и остановки/запуска сервера. Предупреждение с той же картинкой — 5. Скачанный ZIP и пять хешей проверены.
- Данные: 120 случаев (40 dev / 80 test), 41 изображение. Авторская синтетическая разметка без независимой проверки. Семейства/кампании/домены разделены.
- Финальный test: TP30 FP2 TN38 FN10, precision .9375, recall .75, F1 .8333, FPR .05, покрытие .90. Цели precision/recall не достигнуты. Ядро после фиксации не менялось; проверены 63 SHA-256. JSON/CSV, срезы и ошибки в reports.
- 39 backend tests passed; Ruff/pip check/typecheck/ESLint/build passed. Windows setup проверен в отдельной .venv-setup-check; OCR test прошел и там.
- Offline с заблокированными socket connect/DNS до импорта OCR: completed, score 70, 3 OCR-строки, 3 наблюдения, ZIP, 0 попыток сети.
- Браузерная репетиция трех демо/графа/метрик/экспорта — 39,368 с без речи. docs/DEMO.md и PITCH.md распределяют выступление на пять минут.
- Проверены 1366×768, 1440×900 и reflow уменьшенной области, Tab/Escape, длинный URL и казахские строки. IAB Ctrl+Plus не изменил zoom; настоящий zoom 125% не заявляется.
- Gemini без ключа: живого вызова нет; SDK/schema/cache/401/403/503 и fallback проверены. OCR ошибается в символах; поворот 90° плохой. Live external fetch/GPU/Linux и независимый реальный пилот не проверены.
- README, методика, набор, оценка, приемка, источники/лицензии, сценарий/питч/FAQ/roadmap сохранены.

Запуск: powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Offline. Адрес: http://127.0.0.1:8765. Если сервер уже работает, повторная команда не нужна. Зависимости и модели установлены.

Следующий шаг вне ядра: разрешенный пилот с независимой разметкой и новой версией оценки. Не подгонять правила под зафиксированный test; не публиковать localhost-сервис как многопользовательский.
