# Передача SafeTrace KZ · v4

Рабочая папка: `C:\Users\nurbo\Desktop\vvv\safetrace-kz`. [Приложение](http://127.0.0.1:8765/#queue), [подготовленный случай](http://127.0.0.1:8765/#case/e4e5424a4abc4b129c7ad5fc8636345f), [контрпример](http://127.0.0.1:8765/#case/4016da2c3ed0481fb5c7750b717bfb10). Версии: приложение 2.2.1, rules-4.0, pipeline-2.2.1. Это локальный MVP трека 2 для одного аналитика.

## Открыть на этом компьютере

Если страница уже открывается, повторный запуск не нужен. После перезагрузки компьютера:

```powershell
cd C:\Users\nurbo\Desktop\vvv\safetrace-kz
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Offline -Background
.\.venv\Scripts\python.exe scripts\preflight.py --server
```

Остановка: `powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1`. Процесс проверяется по записи запуска; активный анализ мешает остановке. Логи находятся в `logs/server-8765.*.log`. [Подробности](LOCAL_SERVER.md).

## Что показать

- [PDF: что это за программа и как она работает](../output/pdf/SafeTrace-KZ-report-v4.pdf).
- [Шесть редактируемых слайдов](../deliverables/SafeTrace-KZ-defense-v4.pptx), [сценарий](DEMO_V4.md), [речь](PITCH_V4.md), [ответы](FAQ_V4.md).
- [Скачанное досье](../reports/acceptance-v4/main-demo-export/browser-new-case.zip): распаковать целиком, открыть `report.html`.
- [Сравнение на одном новом наборе](../reports/EVALUATION_V4.md) и [разбор всех 12 ошибок](../reports/ERROR_ANALYSIS_V4.md).
- [Матрица приёмки](../reports/ACCEPTANCE_V4.md) и [итог передачи](../reports/HANDOFF_V4.md).

## Новый выпуск и перенос

Каталог `deliverables/releases/v4/`: `SafeTrace-KZ-v4-source.zip`, отдельная резервная копия `SafeTrace-KZ-v4-demo-data.zip`, `SHA256SUMS.txt` и `START-HERE.md`. Исторический выпуск v3 сохранён.

Архив исходников содержит собранный frontend, код, тесты, наборы, исходные оценки, PPTX, PDF и `PACKAGE_MANIFEST.json` с SHA-256 каждого файла. В нём нет `.env`, ключей, рабочей базы, весов моделей, Python-окружения и node_modules. Это исходный проект, а не самостоятельный exe. Данные и история передаются отдельным проверенным архивом.

На новом Windows x64 установить Python 3.12 x64 и Node.js 22.12+; проверены Python 3.12.14 и Node 24.13.1. Нужен ASCII-путь, например `C:\SafeTrace KZ`: пробелы допустимы, кириллица в полном пути моделей не поддерживается закреплённой Windows-библиотекой OCR. Разместить архив данных рядом с папкой проекта.

```powershell
cd 'C:\SafeTrace KZ'
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\.venv\Scripts\python.exe scripts\backup_data.py verify ..\SafeTrace-KZ-v4-demo-data.zip
.\.venv\Scripts\python.exe scripts\backup_data.py restore ..\SafeTrace-KZ-v4-demo-data.zip --to data
.\.venv\Scripts\python.exe scripts\preflight.py
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Offline -Background
```

Восстанавливать до первого запуска; существующая папка `data` не заменяется. При необходимости выбрать новую папку по [BACKUP](BACKUP.md). `setup.ps1 -PythonPath 'C:\Path\Python312\python.exe'` позволяет явно указать Python. Первичная установка требует интернета; после неё локальные OCR, правила, синтетические маршруты, история и экспорт работают без облака. Проверяются девять файлов трёх OCR-моделей по `models-manifest.json`.

В этой итерации candidate ZIP распакован в другую ASCII-папку с пробелом на этом же Windows ПК; модели скопированы, данные восстановлены. Пройдены новый OCR, маршрут, экспорт и перезапуск с совпадением всех строк/оригиналов. Runtime конечного ZIP сверяется с испытанным candidate. Python-окружение использовано уже установленное. Это не чистая установка на другом физическом компьютере. Итог и точные границы — в приёмке и отдельной квитанции рядом с выпуском.

## Какие результаты заявлять

80 новых авторских синтетических случаев, 40+/40−, 32 изображения. На одинаковых входах v3: TP31/FP9/TN31/FN9; v4: TP30/FP2/TN38/FN10. Precision 93,75%, recall 75%, FPR 5%; достаточно данных 74/80. Цели precision≥95% и recall≥80% не достигнуты. На изображениях recall 62,5%; автоматических неверных OCR-адресов 0, но принят на один правильный адрес меньше. Правильная подсказка не считается автоматическим исправлением.

Независимой человеческой разметки, live-пилота внешних сайтов, живого Gemini, Linux и другого физического ПК нет. [Ограничения](LIMITATIONS.md) содержат конкретные нерешённые причины. Числовые веса и ядро после final не менялись; [проверка версии](../scripts/verify_version_v4.py) сверяет ядро, данные, исторические файлы и арифметику результатов.
