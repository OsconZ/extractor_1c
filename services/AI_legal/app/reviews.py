from __future__ import annotations

import html
import json
import math
import re
from typing import Iterable

import httpx

from .llm import build_debug_info, client, extract_reply
from .schemas import LlmDebugInfo, SectionReview

_SYSTEM_PROMPTS = {
    "lawyer": (
        "Ты юрист. Проанализируй шапку, каждый раздел документа и спецификацию после строки 'Инструкция'. "
        "Верни JSON с ключом sections (массив объектов со свойствами title, resume, risks, score, "
        "где score — целое число от 1 до 10) и опциональными ключами INACCURACY (строка или массив), "
        "который содержит перечень ключевых несоответствий по всему документу. RED_FLAGS (строка или массив),"
        "который выводит только ошибку по общей сумме, если она разная на протяжении документа, и ошибку по Сторонам (Покупатель и Поставщик)"
        "если они разные на протяжении документа, в противном случае оставь данный пункт пустым."
        "Внимание: RED_FLAGS заполнять только если есть ошибки! Если ошибок нет, оставить пустым. Если есть любые другие замечания, кроме суммы и сторон - игнорируй их."
        "Возвращай только json, без дополнительных обозначений типа ```json```"
    ),
    "economist": (
        "Ты экономист. Проанализируй финансовые и экономические условия в шапке, каждом разделе и спецификации после строки 'Инструкция'. "
        "Сфокусируйся на ценах, суммах, сроках поставки, валюте, условиях оплаты и показателях эффективности. "
        "Верни JSON с ключом sections (title, resume, risks, score от 1 до 10), а также опциональными INACCURACY и RED_FLAGS с критичными финансовыми несостыковками. "
        "Возвращай только json, без дополнительных обозначений типа ```json```"
    ),
    "accountant": (
        "Ты бухгалтер. Проверь корректность расчетов, налоги (особенно НДС), порядок оформления первичных документов в шапке, каждом разделе и спецификации после строки 'Инструкция'. "
        "Верни JSON с ключом sections (title, resume, risks, score от 1 до 10), добавляя INACCURACY для ошибок учета и RED_FLAGS для критичных несоответствий сумм или налогов. "
        "Возвращай только json, без дополнительных обозначений типа ```json```"
    ),
}


def _pick_system_prompt(role_key: str) -> str:
    return _SYSTEM_PROMPTS.get(role_key, _SYSTEM_PROMPTS["lawyer"])


def _parse_titles(source: str) -> list[str]:
    pattern = re.compile(r"^(Шапка|Раздел\s+\d+|Спецификация):", re.MULTILINE)
    titles: list[str] = []
    for match in pattern.finditer(source):
        titles.append(match.group(1))
    return titles


def _coerce_to_list(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _extract_items_from_parsed(parsed: object) -> list[dict]:
    if isinstance(parsed, dict):
        if "sections" in parsed and isinstance(parsed["sections"], list):
            return _coerce_to_list(parsed["sections"])
        if "items" in parsed and isinstance(parsed["items"], list):
            return _coerce_to_list(parsed["items"])
        if "reviews" in parsed and isinstance(parsed["reviews"], list):
            return _coerce_to_list(parsed["reviews"])
        return _coerce_to_list(parsed)
    return _coerce_to_list(parsed)


def _coerce_red_flags(parsed: object) -> str | None:
    if isinstance(parsed, dict):
        for key in ("red_flags", "RED_FLAGS"):
            if key in parsed and parsed[key]:
                value = parsed[key]
                if isinstance(value, list):
                    return "; ".join(str(item) for item in value if str(item).strip()).strip() or None
                return str(value).strip() or None
    return None


def _coerce_inaccuracy(parsed: object) -> str | None:
    if isinstance(parsed, dict):
        for key in ("inaccuracy", "INACCURACY"):
            if key in parsed and parsed[key]:
                value = parsed[key]
                if isinstance(value, list):
                    return "; ".join(str(item) for item in value if str(item).strip()).strip() or None
                return str(value).strip() or None
    return None


def _looks_like_section(item: dict) -> bool:
    return any(key in item for key in ("title", "resume", "risks", "score"))


def _extract_response_payload(text: str) -> tuple[list[dict], str | None, str | None]:
    try:
        parsed = json.loads(text)
        inaccuracy = _coerce_inaccuracy(parsed)
        red_flags = _coerce_red_flags(parsed)
        items = _extract_items_from_parsed(parsed)
        filtered = [item for item in items if _looks_like_section(item)]
        if filtered:
            return filtered, inaccuracy, red_flags
    except json.JSONDecodeError:
        pass

    matches = re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)
    items: list[dict] = []
    inaccuracy: str | None = None
    red_flags: str | None = None
    for chunk in matches:
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            possible_inaccuracy = _coerce_inaccuracy(parsed)
            inaccuracy = inaccuracy or possible_inaccuracy
            possible_flags = _coerce_red_flags(parsed)
            red_flags = red_flags or possible_flags
            if _looks_like_section(parsed):
                items.append(parsed)
    return items, inaccuracy, red_flags


def _normalize_reviews(raw_items: Iterable[dict], titles: list[str]) -> list[SectionReview]:
    normalized: list[SectionReview] = []
    padded_items = list(raw_items)
    if titles and len(padded_items) < len(titles):
        padded_items.extend({} for _ in range(len(titles) - len(padded_items)))

    for index, item in enumerate(padded_items):
        fallback_title = titles[index] if index < len(titles) else f"Раздел {index + 1}"
        title = str(item.get("title") or fallback_title)
        resume = str(item.get("resume") or "").strip()
        risks = str(item.get("risks") or "").strip()
        score = str(item.get("score") or "").strip()
        normalized.append(
            SectionReview(
                title=title or f"Раздел {index + 1}",
                resume=resume,
                risks=risks,
                score=score,
            )
        )
    return normalized


def _extract_numeric_score(score: str) -> float | None:
    match = re.search(r"([0-9]+(?:[\.,][0-9]+)?)", score)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _calculate_average_score(reviews: list[SectionReview]) -> float | None:
    values = [value for review in reviews if (value := _extract_numeric_score(review.score)) is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _score_to_color(score: float | None) -> str:
    if score is None or math.isnan(score):
        return "#f3f4f6"
    clamped = max(1.0, min(10.0, score))
    hue = 0 + (120 * (clamped - 1) / 9)
    return f"hsl({hue:.0f}, 75%, 90%)"


def _build_html_report(
    reviews: list[SectionReview],
    overall_score: float | None,
    inaccuracy: str | None,
    red_flags: str | None,
    document_html: str | None = None,
) -> str:
    cards = []
    for review in reviews:
        score_numeric = _extract_numeric_score(review.score)
        bg_color = _score_to_color(score_numeric)
        card = f"""
        <section class=\"section-card\" style=\"background:{bg_color}\">
            <h2>{html.escape(review.title)}</h2>
            <div class=\"section-card__score\">Оценка: {html.escape(review.score) or "-"}</div>
            <div class=\"section-card__block\">
                <h3>Резюме</h3>
                <p>{html.escape(review.resume) or "(пусто)"}</p>
            </div>
            <div class=\"section-card__block\">
                <h3>Риски</h3>
                <p>{html.escape(review.risks) or "(пусто)"}</p>
            </div>
        </section>
        """.strip()
        cards.append(card)

    overall_color = _score_to_color(overall_score)
    inaccuracy_block = (
        f"<div class=\"report__block\"><h3>Неточности</h3><p>{html.escape(inaccuracy)}</p></div>"
        if inaccuracy
        else ""
    )
    red_flags_block = (
        f"<div class=\"report__block\"><h3>RED FLAGS</h3><p>{html.escape(red_flags)}</p></div>"
        if red_flags
        else ""
    )

    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 16px; background: #f9fafb; }}
            .report__summary {{ display: flex; gap: 12px; align-items: center; }}
            .report__score {{ padding: 8px 12px; border-radius: 8px; background: {overall_color}; font-weight: bold; }}
            .report__block {{ background: white; border-radius: 10px; padding: 12px; margin: 8px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
            .section-card {{ background: white; border-radius: 10px; padding: 12px; margin: 8px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
            .section-card__score {{ font-weight: bold; margin-bottom: 4px; }}
            .section-card__block {{ margin-top: 8px; }}
            pre {{ white-space: pre-wrap; font-family: Consolas, monospace; }}
        </style>
    </head>
    <body>
        <div class=\"report__summary\">
            <div class=\"report__score\">Средняя оценка: {overall_score if overall_score is not None else "-"}</div>
        </div>
        {inaccuracy_block}
        {red_flags_block}
        {"".join(cards)}
        {f"<hr><h2>Документ</h2>{document_html}" if document_html else ""}
    </body>
    </html>
    """.strip()


async def evaluate_section_file(
    content: str,
    document_html: str | None = None,
    *,
    role_key: str = "lawyer",
) -> tuple[list[SectionReview], float | None, str | None, str | None, str, LlmDebugInfo | None]:
    titles = _parse_titles(content)
    system_prompt = _pick_system_prompt(role_key)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]

    try:
        raw = await client.chat(messages)
    except httpx.HTTPStatusError as exc:
        raise
    debug = build_debug_info(messages, raw)
    reply = extract_reply(raw)
    raw_items, inaccuracy, red_flags = _extract_response_payload(reply)
    if not raw_items and titles:
        raw_items = [{} for _ in titles]
    reviews = _normalize_reviews(raw_items, titles)
    average_score = _calculate_average_score(reviews)
    html_report = _build_html_report(
        reviews,
        average_score,
        inaccuracy,
        red_flags,
        document_html,
    )
    return reviews, average_score, inaccuracy, red_flags, html_report, debug


__all__ = ["evaluate_section_file"]