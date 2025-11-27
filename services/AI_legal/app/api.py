from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Path, UploadFile

from .llm import client
from .reviews import evaluate_section_file
from .schemas import FullProcessingResponse, HealthResponse
from .sections import build_chunks_from_payload, build_sections_instruction, render_document_html
from .settings import get_settings

router = APIRouter(prefix="/api/sections", tags=["sections"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    models_raw = await client.list_models()
    available = [item.get("name") for item in models_raw.get("models", [])]
    return HealthResponse(
        status="ok",
        model=settings.ollama_model,
        ollama=settings.ollama_base_url,
        model_available=settings.ollama_model in available,
    )


@router.post("/full-prepared", response_model=FullProcessingResponse)
async def review_prepared_sections(
    # key: str = Path(..., description="Роль анализа: lawyer/economist/accountant"),
    file: UploadFile = File(...),
) -> FullProcessingResponse:
    raw_bytes = await file.read()
    try:
        payload = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Файл должен быть в кодировке UTF-8") from exc

    normalized_key =  "lawyer"
    if normalized_key not in {"lawyer", "economist", "accountant"}:
        raise HTTPException(status_code=422, detail="Некорректный тип обработки")

    sections, specification_text = build_chunks_from_payload(payload)
    combined_text = build_sections_instruction(sections, specification_text)
    document_html = render_document_html(sections, specification_text)

    _, overall_score, inaccuracy, red_flags, html_report, _ = await evaluate_section_file(
        combined_text,
        document_html,
        role_key=normalized_key,
    )

    return FullProcessingResponse(
        docx_text=document_html,
        specification_text=specification_text,
        overall_score=overall_score,
        inaccuracy=inaccuracy,
        red_flags=red_flags,
        html=html_report,
        debug_message=None,
    )