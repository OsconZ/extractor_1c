from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .document.reader import load_blocks
from .document.spec_extractor import extract_specification_from_blocks
from .services.section_splitter import SectionChunk, split_into_sections

app = FastAPI(title="Document Splitter Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8091"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ANALYZE_SERVICE_URL = os.getenv("ANALYZE_SERVICE_URL", "http://192.168.3.63:10000/analyze")
# возможно localhost
SECTIONS_SERVICE_URL = os.getenv("SECTIONS_SERVICE_URL", "http://ai_legal:8000/api/sections/full")
SECTIONS_FALLBACK_URL = os.getenv(
    "SECTIONS_FALLBACK_URL", "http://ai_legal:8000/api/sections/full-prepared"
)
HTTP_TIMEOUT = float(os.getenv("SERVICE_HTTP_TIMEOUT", "120"))


def _section_to_text(section: SectionChunk) -> str:
    parts = [section.title.strip()] if section.title else []
    if section.content:
        parts.append(section.content.strip())
    return "\n".join(part for part in parts if part)


def _serialize_parts(sections: list[SectionChunk], blocks_html: str) -> dict[str, str]:
    payload: dict[str, str] = {}
    for index in range(16):
        text = ""
        if index < len(sections):
            text = _section_to_text(sections[index])
        payload[f"part_{index}"] = text

    payload["part_16"] = blocks_html
    return payload


def _extract_specification_text(blocks: list[Any]) -> str:
    try:
        spec_result = extract_specification_from_blocks(blocks)
        lines = []
        for table_region in spec_result.tables:
            for row in table_region.block.rows or []:
                row_text = " | ".join(cell.strip() for cell in row)
                lines.append(f"TABLE: {row_text}")

        return "\n".join(lines)
    except Exception:
        return ""


async def _extract_parts(file: UploadFile) -> dict[str, str]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пуст или не содержит данных")

    try:
        blocks = load_blocks(file.filename, content)
    except Exception as exc:  # pragma: no cover - defensive parsing guard
        raise HTTPException(status_code=400, detail=f"Не удалось разобрать файл: {exc}") from exc

    sections = split_into_sections(blocks)
    specification_text = _extract_specification_text(blocks)
    return _serialize_parts(sections, specification_text)


def _parse_response_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


async def _call_analyze_service(client: httpx.AsyncClient, parts: Dict[str, str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "service": "analyze",
        "url": ANALYZE_SERVICE_URL,
        "status": None,
        "response": None,
        "error": None,
    }

    try:
        files = {
            "budget_file": (
                "budget.json",
                json.dumps({"specification": parts.get("part_16", "")}, ensure_ascii=False),
                "application/json",
            ),
            "spec_file": ("sections.json", json.dumps(parts, ensure_ascii=False), "application/json"),
        }

        response = await client.post(ANALYZE_SERVICE_URL, files=files)
        result["status"] = response.status_code
        if response.status_code == 200:
            result["response"] = _parse_response_payload(response)
        else:
            result["error"] = response.text
    except Exception as exc:  # pragma: no cover - defensive external call guard
        result["error"] = str(exc)

    return result


async def _call_sections_service(client: httpx.AsyncClient, parts: Dict[str, str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "service": "sections",
        "url": SECTIONS_SERVICE_URL,
        "status": None,
        "fallback_url": SECTIONS_FALLBACK_URL,
        "fallback_status": None,
        "used_fallback": False,
        "response": None,
        "error": None,
    }

    try:
        files = {
            "file": ("sections.json", json.dumps(parts, ensure_ascii=False), "application/json")
        }
        primary_response = await client.post(SECTIONS_SERVICE_URL, files=files)
        result["status"] = primary_response.status_code
        if primary_response.status_code == 200:
            result["response"] = _parse_response_payload(primary_response)
            return result

        if SECTIONS_FALLBACK_URL:
            result["used_fallback"] = True
            fallback_response = await client.post(SECTIONS_FALLBACK_URL, json=parts)
            result["fallback_status"] = fallback_response.status_code
            if fallback_response.status_code == 200:
                result["response"] = _parse_response_payload(fallback_response)
            else:
                result["error"] = fallback_response.text
        else:
            result["error"] = primary_response.text
    except Exception as exc:  # pragma: no cover - defensive external call guard
        result["error"] = str(exc)

    return result


@app.post("/api/sections/split")
async def split_document(file: UploadFile = File(...)) -> JSONResponse:
    parts = await _extract_parts(file)
    return JSONResponse(content=parts)


@app.post("/api/sections/dispatch")
async def dispatch_sections(file: UploadFile = File(...)) -> JSONResponse:
    parts = await _extract_parts(file)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        analyze_task = asyncio.create_task(_call_analyze_service(client, parts))
        sections_task = asyncio.create_task(_call_sections_service(client, parts))
        service_results = await asyncio.gather(analyze_task, sections_task)

    combined_response = {
        result["service"]: result["response"]
        for result in service_results
        if result.get("response") is not None
    }

    services_mapping: Dict[str, Dict[str, Any]] = {
        result["service"]: result for result in service_results
    }

    return JSONResponse(
        content={
            "parts": parts,
            "combined": combined_response,
            "services": services_mapping,
        }
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}