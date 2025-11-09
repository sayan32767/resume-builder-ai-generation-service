import os
import io
import asyncio
import logging
from fastapi import FastAPI, UploadFile, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pdf_processor import extract_text_from_pdf
from llm_resume_builder import generate_resume_schema
from schema import ResumeResponse
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# Config via ENV (with sane defaults)
# -----------------------------
MAX_FILE_SIZE_MB = float(os.getenv("MAX_FILE_SIZE_MB", "5"))         # e.g. 5 MB
MAX_FILE_SIZE = int(MAX_FILE_SIZE_MB * 1024 * 1024)
LLM_TIMEOUT_SEC = float(os.getenv("LLM_TIMEOUT_SEC", "120"))          # 120 seconds
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
INTERNAL_SECRET = os.getenv("EXPRESS_INTERNAL_SECRET")

print("=== ENVIRONMENT CHECK ===")
print("MAX_FILE_SIZE_MB:", MAX_FILE_SIZE_MB)
print("MAX_FILE_SIZE:", MAX_FILE_SIZE)
print("LLM_TIMEOUT_SEC:", LLM_TIMEOUT_SEC)
print("================================")

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("resume-api")

# -----------------------------
# App + CORS
# -----------------------------
ENV = os.getenv("ENVIRONMENT", "dev")

app = FastAPI(
    docs_url=None if ENV == "prod" else "/docs",
    redoc_url=None if ENV == "prod" else "/redoc",
    openapi_url=None if ENV == "prod" else "/openapi.json"
)

# ALLOWED_ORIGINS can be "*", or "https://a.com,https://b.com"
if ALLOWED_ORIGINS.strip() == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# -----------------------------
# Helpers
# -----------------------------
async def _run_llm_with_timeout(pdf_text: str):
    """
    Your generate_resume_schema is synchronous. We run it in a worker thread
    and enforce an async timeout.
    """
    import anyio
    try:
        return await asyncio.wait_for(
            anyio.to_thread.run_sync(generate_resume_schema, pdf_text),
            timeout=LLM_TIMEOUT_SEC
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="LLM request timed out")

def _is_effectively_empty(payload: dict) -> bool:
    """
    Consider it empty if dict is {} after exclude_none AND all top-level lists are empty.
    """
    if not payload:
        return True

    # If every top-level value is either empty list, empty dict, None, or empty string — treat as empty.
    for v in payload.values():
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        if isinstance(v, (list, dict)) and len(v) == 0:
            continue
        # found something substantive
        return False
    return True

# -----------------------------
# Route
# -----------------------------
@app.post("/process")
async def process_resume(pdf: UploadFile, secret: str = Header(None)):
    if secret != INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


    # 1) Validate presence & type
    if pdf is None:
        raise HTTPException(status_code=400, detail="No PDF uploaded")

    filename = (pdf.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    # 2) Read bytes to check size & hand off safely
    try:
        file_bytes = await pdf.read()
        size = len(file_bytes or b"")
        if size == 0:
            raise HTTPException(status_code=422, detail="Empty PDF uploaded")

        if size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"PDF file too large (>{MAX_FILE_SIZE_MB:.0f} MB)"
            )

        file_like = io.BytesIO(file_bytes)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("PDF read failed")
        return JSONResponse(
            status_code=500,
            content={"error": "PDF read failed", "details": str(e)}
        )

    # 3) Extract PDF text
    try:
        pdf_text = extract_text_from_pdf(file_like)

        if not pdf_text or len(pdf_text.strip()) < 10:
            raise HTTPException(
                status_code=422,
                detail="Could not extract meaningful text from the uploaded PDF"
            )

        logger.info("PDF text extracted (%d chars)", len(pdf_text))

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("PDF extraction failed")
        return JSONResponse(
            status_code=500,
            content={"error": "PDF extraction failed", "details": str(e)}
        )

    # 4) Call LLM with timeout
    try:
        normalized = await _run_llm_with_timeout(pdf_text)

        if not isinstance(normalized, dict):
            raise ValueError("LLM returned non-JSON response")

    except HTTPException:
        # (timeout likely)
        raise
    except Exception as e:
        logger.exception("LLM generation failed")
        return JSONResponse(
            status_code=500,
            content={"error": "LLM generation failed", "details": str(e)}
        )

    # 5) Pydantic validation (drop None automatically)
    try:
        validated = ResumeResponse(**normalized)
        final_output = validated.model_dump(exclude_none=True)

        # If you also want to drop empty lists/objects/empty-strings here,
        # you can run a small normalizer (optional). Keeping as-is per your current logic.

        if _is_effectively_empty(final_output):
            raise HTTPException(
                status_code=422,
                detail="No usable resume data could be extracted"
            )

        return final_output

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Schema validation failed")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Schema validation failed (LLM returned invalid JSON)",
                "details": str(e),
                "raw": normalized
            }
        )

    # Safety fallback
    return JSONResponse(
        status_code=500,
        content={"error": "Unknown server error"}
    )
