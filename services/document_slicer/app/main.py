from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
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
AI_LEGAL_SERVICE_URL = os.getenv("AI_LEGAL_SERVICE_URL", "http://ai_legal:8000/api/sections/full")

HTTP_TIMEOUT = float(os.getenv("SERVICE_HTTP_TIMEOUT", "120"))
DATA_VOLUME_PATH = Path(os.getenv("DATA_VOLUME_PATH", "/data"))
SECTIONS_FILE_NAME = os.getenv("SECTIONS_FILE_NAME", "sections.json")
PART_16_FILE_NAME = os.getenv("PART_16_FILE_NAME", "part_16.json")
BUDGET_FILE_PATH = Path(
    os.getenv("BUDGET_FILE_PATH", str(DATA_VOLUME_PATH / "budget.json"))
)

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


def _persist_sections(parts: dict[str, str]) -> dict[str, Path]:
    DATA_VOLUME_PATH.mkdir(parents=True, exist_ok=True)

    sections_path = DATA_VOLUME_PATH / SECTIONS_FILE_NAME
    part_16_path = DATA_VOLUME_PATH / PART_16_FILE_NAME

    try:
        sections_path.write_text(
            json.dumps(parts, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        part_16_payload = parts.get("part_16", "")
        part_16_path.write_text(
            json.dumps(part_16_payload, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except OSError:
        # Непринципиально для пользователя; ошибки прокинутся в лог
        pass

    return {"sections": sections_path, "part_16": part_16_path}


def _parse_response_payload(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text

async def _call_analyze_service(
    client: httpx.AsyncClient, part_16_path: Path
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "service": "analyze",
        "url": ANALYZE_SERVICE_URL,
        "status": None,
        "response": None,
        "error": None,
    }

    if not BUDGET_FILE_PATH.exists():
        result["error"] = f"Budget file not found at {BUDGET_FILE_PATH}"
        return result

    try:
        part_16_payload = part_16_path.read_text(encoding="utf-8")
    except OSError as exc:
        result["error"] = f"Failed to read part_16 payload: {exc}"
        return result

    files = {
        "budget": (
            BUDGET_FILE_PATH.name,
            BUDGET_FILE_PATH.open("rb"),
            "application/octet-stream",
        ),
        "part_16": ("part_16.json", part_16_payload, "application/json"),
    }

    try:
        response = await client.post(ANALYZE_SERVICE_URL, files=files)
        result["status"] = response.status_code
        if response.status_code == 200:
            result["response"] = _parse_response_payload(response)
        else:
            result["error"] = response.text
    except Exception as exc:  # pragma: no cover - defensive external call guard
        result["error"] = str(exc)
    finally:
        try:
            files["budget"][1].close()
        except Exception:
            pass

    return result


async def _call_ai_legal_service(client: httpx.AsyncClient, parts: Dict[str, str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "service": "ai_legal",
        "url": AI_LEGAL_SERVICE_URL,
        "status": None,
        "response": None,
        "error": None,
    }

    try:
        primary_response = await client.post(AI_LEGAL_SERVICE_URL, json=parts)
        result["status"] = primary_response.status_code
        if primary_response.status_code == 200:
            result["response"] = _parse_response_payload(primary_response)
        else:
            result["error"] = primary_response.text
    except Exception as exc:  # pragma: no cover - defensive external call guard
        result["error"] = str(exc)

    return result


@app.post("/api/sections/split")
async def split_document(file: UploadFile = File(...)) -> JSONResponse:
    parts = await _extract_parts(file)
    _persist_sections(parts)
    return JSONResponse(content=parts)


@app.post("/api/sections/dispatch")
async def dispatch_sections(file: UploadFile = File(...)) -> JSONResponse:
    parts = await _extract_parts(file)
    saved_paths = _persist_sections(parts)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        analyze_task = asyncio.create_task(
            _call_analyze_service(client, saved_paths["part_16"])
        )
        ai_legal_task = asyncio.create_task(_call_ai_legal_service(client, parts))
        service_results = await asyncio.gather(analyze_task, ai_legal_task)

    responses = {
        result["service"]: (
            result["response"]
            if result.get("response") is not None
            else {"error": result.get("error"), "status": result.get("status")}
        )
        for result in service_results
    }
    return JSONResponse(content=responses)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}