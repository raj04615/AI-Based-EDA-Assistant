Project root ke liye complete, production-grade **`README.md`** file ka content niche diya gaya hai. Isme system architecture, multi-format pipeline, installation steps aur API documentation sab shamil hain:

```markdown
# AI-Based EDA Assistant v3.0

An enterprise-grade, decoupled Retrieval-Augmented Generation (RAG) system built to analyze organizational reports, financial statements, annual filings, academic placement statistics, presentations, spreadsheets, and data-heavy documents across 10+ file formats.

Features a high-performance **FastAPI** backend paired with a modern **Next.js 14 / React 18 TypeScript** split-pane workspace. Users can ingest documents individually or via batch ZIP archives, inspect canonical Markdown views, submit natural language queries, and receive token-by-token streaming responses with interactive page, slide, and row citations.

---

## Key Features

- **Multi-Format Ingestion:** Deep extraction for `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.txt`, `.md`, and image OCR (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff` via Tesseract).
- **Batch ZIP Uploads:** Ingest ZIP archives containing up to 15 documents with isolated background processing tasks.
- **Magic-Byte Format Verification:** Inspects binary headers before extension fallback to prevent file spoofing or corrupted processing.
- **Canonical Markdown Normalization:** Standardizes multi-format documents into clean Markdown with YAML front matter metadata under `processed/{doc_id}.md`.
- **Table- & Sentence-Aware Chunking:** Preserves Markdown tables intact while chunking narrative text at sentence boundaries (~600 chars, 80-char overlap).
- **Pinecone Namespace Isolation:** Isolates vectors and metadata per document using `namespace=doc_id`.
- **Anti-Hallucination Guard:** Enforces a strict cosine similarity threshold (rejects matches below 0.35).
- **Real-Time Token Streaming:** Low-latency Server-Sent Events (SSE) streaming powered by **Groq's Meta Llama 3.3 70B**.
- **Conversational Memory:** Retains the last 4 Q&A turns per document session for context-aware follow-ups.
- **Optimistic Document Deletion:** Instant UI removal (<10ms) with background filesystem and vector namespace purging.
- **Resilience & Rate Limiting:** Tenacity exponential backoff retries and SlowAPI rate limiting (10 uploads/min, 20 queries/min).

---

## System Architecture


```

INPUT DOCUMENTS                 VECTOR ENGINE (CENTRAL)               AI INTELLIGENCE & OUTPUT
┌──────────────────┐                                             ┌──────────────────────────┐
│ 📊 TABLES / CSV  │───┐                                         │   🔍 SEMANTIC SEARCH     │
│ (XLSX, CSV, 50r) │   │                                         │   (Cosine Sim > 0.35)    │
└──────────────────┘   │                                         └────────────┬─────────────┘
┌──────────────────┐   │     ┌─────────────────────────────┐                  │
│ 📑 DOCUMENTS     │───┼────►│  PINECONE SERVERLESS INDEX  │─────────────────►│   ⚡ META LLAMA 3.3   │
│ (PDF, DOCX, PPTX)│   │     │  • Namespace = doc_id       │   (SSE Stream)   │   (70B via Groq API) │
└──────────────────┘   │     │  • BGE-Small-en-v1.5 (384d) │                  └───────────┬──────────┘
┌──────────────────┐   │     └─────────────────────────────┘                              │
│ 🖼️ OCR & LOGS    │───┘                                                                  │
│ (PNG, JPG, TXT)  │                                                                      ▼
└──────────────────┘                                                         ┌──────────────────────────┐
│ 🗄️ SQLITE + CITATIONS    │
│ (4-Turn Memory, Live UI) │
└──────────────────────────┘

```

---

## Tech Stack

| Layer | Technologies Used |
| :--- | :--- |
| **Backend Framework** | Python 3.12+, FastAPI, Uvicorn, Pydantic v2, SlowAPI, asyncio |
| **Frontend Framework** | Next.js 14 (App Router), React 18, TypeScript, Vanilla CSS (Variables) |
| **Database** | SQLite3 (`eda_assistant.db`) with PRAGMA safe schema migrations |
| **Vector Store** | Pinecone Serverless Index (Cosine Similarity, Namespaced) |
| **Embeddings** | SentenceTransformers (`BAAI/bge-small-en-v1.5`, 384-d) |
| **LLM Inference** | Groq API (`Meta Llama 3.3 70B Versatile` SSE Streaming) |
| **Document Parsers** | `pdfplumber`, `PyPDF`, `python-docx`, `python-pptx`, `pandas`, `openpyxl`, `pytesseract` |
| **Testing & CI** | Pytest (pipeline, multi-format, and normalization test suites) |
| **Deployment** | Docker, Docker Compose |

---

## Project Structure


```

├── backend/app/              # Modular backend services, routes, and database
│   ├── database/             # SQLite connection and migration models
│   ├── routes/               # API endpoints (/upload, /documents, /chat, /health)
│   └── services/             # Ingestion, normalization, chunking, vector, LLM services
├── frontend/                 # Next.js 14 split-pane user interface
│   ├── app/                  # App Router pages and theme styles
│   ├── components/           # UploadZone, ChatWindow, CitationCard, DocumentViewer
│   └── lib/                  # Backend HTTP & SSE API client
├── tests/                    # Pytest integration & unit test suite
├── uploads/                  # Temporary document storage
├── processed/                # Normalized Markdown files ({doc_id}.md)
├── app.py                    # Root FastAPI entrypoint
├── Dockerfile                # Backend container configuration
└── docker-compose.yml        # Docker compose specification

```

---

## Getting Started

### Prerequisites
- Python 3.12+
- Node.js 18+ and npm
- Tesseract OCR (optional, for image processing)
- Groq API Key & Pinecone API Key

### 1. Clone & Configure Environment
```bash
git clone [https://github.com/raj04615/AI-Based-EDA-Assistant.git](https://github.com/raj04615/AI-Based-EDA-Assistant.git)
cd AI-Based-EDA-Assistant

```

Create a `.env` file in the root directory:

```env
GROQ_API_KEY=your_groq_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=eda-assistant

```

### 2. Backend Setup

```bash
# Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run FastAPI backend
uvicorn app:app --reload --port 8000

```

Backend API documentation will be available at `http://localhost:8000/docs`.

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev

```

Open `http://localhost:3000` to access the split-pane workspace.

---

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Health status check |
| `POST` | `/upload` | Upload single document or ZIP archive (Rate: 10/min) |
| `GET` | `/status/{doc_id}` | Poll ingestion pipeline status |
| `GET` | `/documents` | List all registered documents |
| `GET` | `/documents/{doc_id}/history` | Retrieve conversational session history |
| `GET` | `/documents/{doc_id}/markdown` | Retrieve normalized Markdown representation |
| `POST` | `/ask/stream` | Stream Q&A response via Server-Sent Events (Rate: 20/min) |
| `DELETE` | `/documents/{doc_id}` | Delete document, vectors, and local files |

---

## Running Tests

Execute the automated test suite with Pytest:

```bash
pytest tests/test_pipeline.py
pytest tests/test_multi_format.py
pytest tests/test_normalization.py

```

```

---

### Isse apne GitHub repository par add aur push karne ke steps:

1. Apne root project folder mein **`README.md`** naam ki file banayein aur upar ka text usme paste karke save karein[cite: 3]।
2. Terminal (PowerShell) mein niche diye gaye commands run karein:

```powershell
git add README.md
git commit -m "docs: add comprehensive README with architecture, setup, and endpoints"
git push origin main

```
