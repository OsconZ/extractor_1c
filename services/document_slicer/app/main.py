from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

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


@app.post("/api/sections/split")
async def split_document(file: UploadFile = File(...)) -> JSONResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пуст или не содержит данных")

    try:
        blocks = load_blocks(file.filename, content)
    except Exception as exc:  # pragma: no cover - defensive parsing guard
        raise HTTPException(status_code=400, detail=f"Не удалось разобрать файл: {exc}") from exc

    sections = split_into_sections(blocks)

    specification_text  = ""
    try:
        spec_result = extract_specification_from_blocks(blocks)
        lines = []
        for table_region in spec_result.tables:
            for row in table_region.block.rows or []:
                row_text = " | ".join(cell.strip() for cell in row)
                lines.append(f"TABLE: {row_text}")

        specification_text = "\n".join(lines)
    except Exception:
        specification_text = ""

    parts = _serialize_parts(sections, specification_text)
    return JSONResponse(content=parts)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}