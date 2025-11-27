from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import json
import os
import requests

app = FastAPI(title="Purchase Analysis API")

# Конфигурация LLM из переменных окружения
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "localhost")  # без http://
OLLAMA_PORT = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")

LLM_CONFIG = {
    "url": f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat",
    "model": OLLAMA_MODEL,
    "temperature": 0.1,
    "max_tokens": 2000,
    "timeout": 60,
}


def get_category_from_llm(item_name: str, available_categories: list) -> str:
    """
    Определение категории товара с помощью LLM.
    Возвращает конкретную категорию из available_categories
    либо "Неопределенная категория".
    """

    prompt = f"""
    Определи к какой категории относится следующий товар: "{item_name}"
    
    Доступные категории:
    {', '.join(available_categories)}
    
    Верни ТОЛЬКО название категории без каких-либо дополнительных объяснений, комментариев или пунктуации.
    """

    try:
        payload = {
            "model": LLM_CONFIG["model"],
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": LLM_CONFIG["temperature"],
                "num_predict": LLM_CONFIG["max_tokens"],
            },
        }

        response = requests.post(
            LLM_CONFIG["url"],
            json=payload,
            timeout=LLM_CONFIG["timeout"],
        )

        if response.status_code == 200:
            result = response.json()
            # Формат ответа Ollama: {"message": {"content": "..."}}
            category = result["message"]["content"].strip()
            # Очистка ответа
            category = (
                category.replace(".", "")
                .replace('"', "")
                .replace("'", "")
                .strip()
            )

            return category if category in available_categories else "Неопределенная категория"
        else:
            return "Неопределенная категория"

    except Exception:
        return "Неопределенная категория"


@app.post("/analyze")
async def analyze_purchases(
    budget_file: UploadFile = File(..., description="JSON файл с бюджетом"),
    spec_file: UploadFile = File(..., description="JSON файл со спецификацией товаров"),
):
    """
    Анализ покупок на основе загруженных файлов:
    - budget.json  (массив объектов с КатегорияБюджета и ДоступныйЛимит)
    - spec.json    (объект с полем items — список товаров)
    """

    # Валидация типов файлов
    if not budget_file.filename.endswith(".json") or not spec_file.filename.endswith(".json"):
        raise HTTPException(400, "Оба файла должны быть в формате JSON")

    try:
        # Чтение и парсинг budget.json
        budget_content = await budget_file.read()
        budget_data = json.loads(budget_content)

        # Чтение и парсинг spec.json
        spec_content = await spec_file.read()
        spec_data = json.loads(spec_content)

    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Ошибка парсинга JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файлов: {str(e)}")

    # Валидация структуры budget данных
    if not isinstance(budget_data, list):
        raise HTTPException(400, "Budget файл должен содержать массив")

    for item in budget_data:
        if not all(key in item for key in ["КатегорияБюджета", "ДоступныйЛимит"]):
            raise HTTPException(
                400,
                "Budget файл должен содержать поля 'КатегорияБюджета' и 'ДоступныйЛимит'",
            )

    # Валидация структуры spec данных
    if not isinstance(spec_data, dict) or "items" not in spec_data:
        raise HTTPException(400, "Spec файл должен содержать объект с полем 'items'")

    if not isinstance(spec_data["items"], list):
        raise HTTPException(400, "Поле 'items' в spec файле должно быть массивом")

    for item in spec_data["items"]:
        if not all(key in item for key in ["name", "qty", "unit", "price", "amount"]):
            raise HTTPException(
                400,
                "Каждый товар должен содержать поля: name, qty, unit, price, amount",
            )

    try:
        # Создаем словарь бюджетов
        budget_dict = {
            item["КатегорияБюджета"]: item["ДоступныйЛимит"] for item in budget_data
        }
        available_categories = list(budget_dict.keys())

        categorized_items: dict[str, list] = {}
        llm_requests_count = 0

        # Обрабатываем каждый товар
        for item in spec_data["items"]:
            category = get_category_from_llm(item["name"], available_categories)
            llm_requests_count += 1

            if category not in categorized_items:
                categorized_items[category] = []

            categorized_items[category].append(
                {
                    "название": item["name"],
                    "количество": item["qty"],
                    "единица_измерения": item["unit"],
                    "цена_за_единицу": item["price"],
                    "сумма_покупки": item["amount"],
                }
            )

        # Формируем отчет по категориям
        category_report = []
        for category, items in categorized_items.items():
            total_amount = sum(item["сумма_покупки"] for item in items)
            available_budget = budget_dict.get(category, 0)

            status = "хватает" if available_budget >= total_amount else "не хватает"
            needed_amount = max(0, total_amount - available_budget)

            category_report.append(
                {
                    "Категория": category,
                    "Бюджет категории": available_budget,
                    "Общая сумма товаров": total_amount,
                    "Необходимая сумма": needed_amount,
                    "Статус": status,
                    "Товары": items,
                }
            )

        return {
            "status": "success",
            "category_report": category_report,
            "llm_requests_count": llm_requests_count,
        }

    except Exception as e:
        raise HTTPException(500, f"Ошибка при анализе: {str(e)}")


@app.get("/")
async def root():
    """Проверка работы API"""
    return {"message": "Purchase Analysis API is working!", "status": "ok"}
