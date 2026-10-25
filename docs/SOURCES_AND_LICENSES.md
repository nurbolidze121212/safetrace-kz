Собственный исходный код проекта распространяется под [MIT](../LICENSE), выбранной автором 25.10.2026. Модели, библиотеки и сторонние материалы сохраняют свои условия.

# Источники и лицензии

Проверено при реализации 20–21 октября 2026. Зависимости зафиксированы в `requirements.lock.txt` и `frontend/package-lock.json`; полный машинный перечень установленного окружения и лицензионных метаданных — `reports/dependencies.json`. Метаданные не заменяют полный текст лицензии конкретного пакета.

Для передачи собранного интерфейса сохранены [полные лицензионные файлы React, React DOM, Scheduler, Cytoscape, Lucide и Vite](../licenses/frontend/README.md), скопированные из установленных пакетов без изменений.

| Компонент | Источник | Лицензия основного проекта |
|---|---|---|
| PaddleOCR / PaddlePaddle | [OCR API](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html), [языки](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md) | Apache-2.0 |
| Cyrillic recognizer | [Карточка модели](https://huggingface.co/PaddlePaddle/cyrillic_PP-OCRv5_mobile_rec) | Apache-2.0 по model card |
| English recognizer v4 | [en_PP-OCRv5_mobile_rec](https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec) | Apache-2.0 по официальной карточке; сверено 22.10.2026 |
| Mobile detector | [Карточка модели](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det) | Apache-2.0 по model card |
| FastAPI | [Официальная документация](https://fastapi.tiangolo.com/) | MIT |
| Pydantic | [Документация](https://docs.pydantic.dev/latest/) | MIT |
| React | [Документация](https://react.dev/) | MIT |
| Vite | [Требования и сборка](https://vite.dev/guide/) | MIT |
| TypeScript | [Официальный проект](https://github.com/microsoft/TypeScript) | Apache-2.0 |
| Cytoscape.js | [API и типы графа](https://js.cytoscape.org/) | MIT |
| Lucide | [Официальный проект](https://lucide.dev/) | ISC |
| Pillow | [Документация](https://pillow.readthedocs.io/) | MIT-CMU / HPND по установленным метаданным |
| google-genai | [Python SDK](https://github.com/googleapis/python-genai) | Apache-2.0 |
| OpenCV 4.10 / opencv-contrib-python | [QR API](https://docs.opencv.org/4.10.0/d7/d90/classcv_1_1GraphicalCodeDetector.html), [лицензия 4.10](https://github.com/opencv/opencv/blob/4.10.0/LICENSE) | Apache-2.0 для OpenCV 4.10; состав бинарного wheel содержит дополнительные лицензии |

Gemini: [изображения](https://ai.google.dev/gemini-api/docs/image-understanding), [структурированный ответ](https://ai.google.dev/gemini-api/docs/structured-output), [модели](https://ai.google.dev/gemini-api/docs/models). Идентификатор `gemini-3.8-flash` найден в официальном примере на дату реализации. SDK-конфигурация и схема проверены локально; доступность реального аккаунта/модели не проверялась без ключа.

Защита переходов: [OWASP SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html). MVP использует allowlist и pinning IP; это не заявление о сертифицированной защите.

Контент: [Telegram Content Licensing](https://telegram.org/tos/content-licensing). Реальный сбор Telegram не реализован. Для пилота нужны отдельные разрешения на конкретные данные; публичный доступ не заменяет такие разрешения.

Изображения и тексты корпуса созданы внутри проекта. Windows Arial используется для локального рендеринга; файл шрифта не включен. Синтетические домены `.test` не принадлежат реальным игровым ресурсам.

Условия хакатона первоначально взяты из SPEC.md. 22 октября дополнительно прочитаны и визуально просмотрены четыре страницы локального PDF; результат — [сопоставление с брифом](HACKATHON_GAP_ANALYSIS.md). В документе: 22 октября 2026, Шымкент, MVP и питч 5 минут; лимит «48 часов» не утверждается. Синтетические данные разрешены; численные ориентиры precision/recall проекта не являются требованиями организаторов.

В v4 добавлена третья локальная модель для предложений при сверке URL. Источник весов — официальный Paddle BOS, URL и SHA-256 всех девяти файлов записаны в models-manifest.json. В архив исходников веса не включены; setup скачивает и проверяет их. Это не изменение лицензии или удалённая отправка изображений.
