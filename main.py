from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from github_fetcher import fetch_github_data
from pdf_processor import extract_text_from_pdf
from llm_resume_builder import generate_resume_schema
from schema import ResumeResponse

app = FastAPI()

@app.post("/process")
async def process_resume(pdf: UploadFile):
    # 1 Validate file exists
    if pdf is None:
        raise HTTPException(status_code=400, detail="No PDF uploaded")

    # 2 Validate file type
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")

    try:
        # 3 Extract PDF text
        pdf_text = extract_text_from_pdf(pdf.file)

        if not pdf_text or len(pdf_text.strip()) < 10:
            raise HTTPException(
                status_code=422,
                detail="Could not extract meaningful text from the uploaded PDF"
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "PDF extraction failed", "details": str(e)}
        )

    try:
        # 4 Send to LLM
        normalized = generate_resume_schema(pdf_text)

        if not isinstance(normalized, dict):
            raise ValueError("LLM returned non-JSON response")

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "LLM generation failed", "details": str(e)}
        )

    try:
        validated = ResumeResponse(**normalized)
        final_output = validated.model_dump(exclude_none=True)

        # ✅ Detect: after trimming empty lists / None, we got {}
        if not final_output:  
            raise HTTPException(
                status_code=422,
                detail="No usable resume data could be extracted"
            )

        return final_output

    except HTTPException:
        raise   # rethrow FastAPI HTTP errors directly

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Schema validation failed (LLM returned invalid JSON)",
                "details": str(e),
                "raw": normalized
            }
        )

    # safety fallback
    return JSONResponse(
        status_code=500,
        content={"error": "Unknown server error"}
    )
