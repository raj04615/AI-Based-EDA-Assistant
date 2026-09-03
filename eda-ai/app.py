"""
FastAPI Backend — Multi-format & ZIP upload pipeline, status polling, document registry, SSE streaming, and rate limiting.
"""

import os
import uuid
import zipfile
import tempfile
import asyncio
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import config
import database
import ingestion
import retrieval

# ── App & Rate Limiter Setup ──────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AI-Based EDA Assistant", version="2.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── Request Models ────────────────────────────────────────────────────

class QuestionStreamRequest(BaseModel):
    doc_id: str = Field(..., description="Document UUID namespace")
    question: str = Field(..., description="User query text")

# ── Routes ────────────────────────────────────────────────────────────

@app.get("/")
async def home(request: Request):
    """Serve the split-pane frontend workspace."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
@limiter.limit("10/minute")
async def upload_document(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload a document (.pdf, .docx, .pptx, .xlsx, .csv, .txt, .md, images) or a .zip archive.
    Validates format via magic byte signatures, processes ZIP archives, registers DB metadata,
    and dispatches isolated background ingestion tasks per file.
    """
    original_filename = file.filename or "uploaded_file"
    ext = os.path.splitext(original_filename)[1].lower()

    contents = await file.read()
    file_size = len(contents)

    if file_size == 0:
        return JSONResponse(
            status_code=400,
            content={"message": "Uploaded file is empty."}
        )

    # Save to a temporary file for format detection & unpacking
    temp_fd, temp_path = tempfile.mkstemp(suffix=ext, dir=config.UPLOAD_DIR)
    try:
        with os.fdopen(temp_fd, "wb") as f:
            f.write(contents)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": f"Failed to receive file: {str(e)}"}
        )

    detected_type = ingestion.detect_file_type(temp_path)

    # Reject unsupported formats
    if detected_type == "unknown":
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return JSONResponse(
            status_code=400,
            content={"message": f"Unsupported or corrupted document format '{ext}'."}
        )

    # ── ZIP Archive Upload Flow ─────────────────────────────────────────
    if detected_type == "zip":
        if not zipfile.is_zipfile(temp_path):
            os.remove(temp_path)
            return JSONResponse(
                status_code=400,
                content={"message": "Corrupted or invalid ZIP archive file."}
            )

        created_docs = []
        skipped_files = []

        try:
            with zipfile.ZipFile(temp_path, "r") as z:
                zip_entries = [info for info in z.infolist() if not info.is_dir()]

                for entry in zip_entries:
                    raw_name = os.path.basename(entry.filename)
                    # Ignore system/hidden files
                    if not raw_name or raw_name.startswith(".") or raw_name.startswith("__MACOSX"):
                        continue

                    entry_ext = os.path.splitext(raw_name)[1].lower()

                    # Enforce file count limit
                    if len(created_docs) >= config.MAX_ZIP_FILES:
                        skipped_files.append({
                            "filename": raw_name,
                            "reason": f"Exceeded maximum ZIP limit of {config.MAX_ZIP_FILES} files."
                        })
                        continue

                    # Reject nested ZIP files
                    if entry_ext == ".zip":
                        skipped_files.append({
                            "filename": raw_name,
                            "reason": "Nested ZIP archives are not supported."
                        })
                        continue

                    # Enforce individual file size limit
                    if entry.file_size > config.MAX_FILE_SIZE_BYTES:
                        skipped_files.append({
                            "filename": raw_name,
                            "reason": f"File size exceeds maximum limit of {config.MAX_FILE_SIZE_MB}MB."
                        })
                        continue

                    # Extract content to temp file for signature check
                    entry_data = z.read(entry.filename)
                    sub_temp_fd, sub_temp_path = tempfile.mkstemp(suffix=entry_ext, dir=config.UPLOAD_DIR)
                    with os.fdopen(sub_temp_fd, "wb") as sf:
                        sf.write(entry_data)

                    sub_type = ingestion.detect_file_type(sub_temp_path)

                    if sub_type == "unknown" or sub_type == "zip":
                        os.remove(sub_temp_path)
                        skipped_files.append({
                            "filename": raw_name,
                            "reason": f"Unsupported format '{entry_ext}'."
                        })
                        continue

                    # Valid document inside ZIP: assign doc_id and save
                    doc_id = str(uuid.uuid4())
                    final_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}{entry_ext}")
                    os.replace(sub_temp_path, final_path)

                    # Register in SQLite & dispatch isolated background task
                    database.create_document(doc_id, raw_name, entry.file_size, file_type=sub_type)
                    background_tasks.add_task(ingestion.run_ingestion_pipeline, doc_id, final_path, sub_type)

                    created_docs.append({
                        "doc_id": doc_id,
                        "filename": raw_name,
                        "file_type": sub_type,
                        "status": "processing"
                    })

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        if not created_docs and skipped_files:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "No valid documents found in ZIP archive.",
                    "skipped": skipped_files
                }
            )

        return {
            "batch": True,
            "documents": created_docs,
            "skipped": skipped_files,
            "message": f"ZIP uploaded. Ingestion initiated for {len(created_docs)} document(s)."
        }

    # ── Single Document Upload Flow ─────────────────────────────────────
    if file_size > config.MAX_FILE_SIZE_BYTES:
        os.remove(temp_path)
        return JSONResponse(
            status_code=400,
            content={"message": f"File size exceeds limit of {config.MAX_FILE_SIZE_MB}MB."}
        )

    doc_id = str(uuid.uuid4())
    final_path = os.path.join(config.UPLOAD_DIR, f"{doc_id}{ext}")
    os.replace(temp_path, final_path)

    # Register in SQLite database
    doc_record = database.create_document(doc_id, original_filename, file_size, file_type=detected_type)

    # Dispatch background ingestion task
    background_tasks.add_task(ingestion.run_ingestion_pipeline, doc_id, final_path, detected_type)

    return {
        "batch": False,
        "doc_id": doc_id,
        "filename": original_filename,
        "file_type": detected_type,
        "status": "processing",
        "documents": [doc_record],
        "skipped": [],
        "message": "Upload successful. Document ingestion initiated."
    }


@app.get("/status/{doc_id}")
async def get_document_status(doc_id: str):
    """Poll ingestion status for a document."""
    doc = database.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@app.get("/documents")
async def list_all_documents():
    """List all registered documents for sidebar navigation."""
    return database.list_documents()


@app.get("/documents/{doc_id}/history")
async def get_document_chat_history(doc_id: str):
    """Retrieve chat history session for a document."""
    doc = database.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    history = database.get_recent_chat_history(doc_id, limit=20)
    return {"doc_id": doc_id, "history": history}


@app.get("/document/{doc_id}/markdown")
@app.get("/documents/{doc_id}/markdown")
async def get_document_markdown(doc_id: str):
    """Retrieve raw normalized Markdown representation for a document."""
    doc = database.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    md_path = doc.get("markdown_path")
    if not md_path or not os.path.exists(md_path):
        fallback_path = os.path.join(config.PROCESSED_DIR, f"{doc_id}.md")
        if os.path.exists(fallback_path):
            md_path = fallback_path

    if not md_path or not os.path.exists(md_path):
        raise HTTPException(
            status_code=404,
            detail="Markdown representation not available for this document."
        )

    with open(md_path, "r", encoding="utf-8", errors="replace") as f:
        md_content = f.read()

    return Response(content=md_content, media_type="text/markdown; charset=utf-8")


def _purge_pinecone_namespace(doc_id: str):
    try:
        index = retrieval.get_pinecone_index()
        index.delete(delete_all=True, namespace=doc_id)
    except Exception as e:
        print(f"[WARN] Failed to purge Pinecone namespace {doc_id}: {e}")


def _cleanup_local_files(doc_id: str):
    """Remove uploaded file and processed markdown from disk (runs in a thread)."""
    # Remove local upload file matching doc_id
    try:
        for fname in os.listdir(config.UPLOAD_DIR):
            if fname.startswith(doc_id):
                try:
                    os.remove(os.path.join(config.UPLOAD_DIR, fname))
                except Exception:
                    pass
    except Exception:
        pass

    # Remove processed markdown file matching doc_id
    processed_md = os.path.join(config.PROCESSED_DIR, f"{doc_id}.md")
    try:
        if os.path.exists(processed_md):
            os.remove(processed_md)
    except Exception:
        pass


@app.delete("/documents/{doc_id}")
async def delete_document_record(doc_id: str, background_tasks: BackgroundTasks):
    """Delete a document, local stored files, and database records instantly; offload Pinecone purge to background."""
    doc = database.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Delete SQLite records immediately (fast, <1ms)
    database.delete_document(doc_id)

    # Offload slow filesystem I/O to a thread so we don't block the event loop
    background_tasks.add_task(asyncio.to_thread, _cleanup_local_files, doc_id)

    # Offload Pinecone cloud deletion to background task
    background_tasks.add_task(_purge_pinecone_namespace, doc_id)

    return {"message": f"Document {doc_id} and associated resources deleted successfully."}


@app.post("/ask/stream")
@limiter.limit("20/minute")
async def ask_question_stream(request: Request, payload: QuestionStreamRequest):
    """
    Accept a natural language question and stream the response via Server-Sent Events (SSE).
    """
    doc_id = payload.doc_id.strip()
    question = payload.question.strip()

    if not doc_id:
        raise HTTPException(status_code=400, detail="Missing doc_id parameter.")

    if not question:
        raise HTTPException(status_code=400, detail="Please provide a question.")

    # Verify document exists and is ready
    doc = database.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc["status"] != "ready":
        raise HTTPException(
            status_code=400,
            detail=f"Document is not ready yet. Current status: {doc['status']}"
        )

    return StreamingResponse(
        retrieval.generate_answer_stream(doc_id, question),
        media_type="text/event-stream"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

