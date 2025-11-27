# AI Lawyer Service

Небольшой сервис FastAPI, адаптированный от эндпойнта `/sections/full`. Он **принимает JSON‑файл, уже нарезанный на секции** (результат `document_slicer`) и возвращает HTML‑отчёт вместе с секциями и спецификацией.

## Эндпойнты
- `POST /api/sections/full` — принимает файл (`file`) c JSON вида `{"part_0": "...", ..., "part_16": "..."}` и возвращает:
  - `docx_text` — HTML с карточками секций.
  - `specification_text` — спецификация как JSON‑строка (если передан `spec_json`) либо HTML из `part_16`.
  - `html` — сгенерированный отчёт.
  - `sections` — массив секций (`part_0`–`part_14`).
  - `specification_json` — переданный блок `spec_json`, если он есть.
  - `overall_score`, `inaccuracy`, `red_flags`, `debug_message` — диагностические поля.
- `GET /health` — проверка готовности.

## Интеграция с Ollama
- переменные окружения:
  - `OLLAMA_HOST` — адрес Ollama API (по умолчанию `http://localhost:11434`).
  - `OLLAMA_MODEL` — имя модели (по умолчанию `llama3`).
- сервис обращается к `/api/chat`, просит модель вернуть JSON с ключами `overall_score`, `summary`, `risks`, `red_flags`, `inaccuracy`. Ответ сохраняется в `ai_summary`, `ai_risks`, `ai_raw_response`, `overall_score`, `inaccuracy`, `red_flags`.