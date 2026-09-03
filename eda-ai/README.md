# AI-Based EDA Assistant

An AI-powered Data Analyst for organizational reports. Upload a PDF document and ask analytical questions in natural language — the assistant retrieves relevant context and generates data-driven answers with page references.

---

## Tech Stack

| Component        | Technology                |
|------------------|---------------------------|
| Backend          | Python 3.12+, FastAPI     |
| Frontend         | HTML, CSS, Vanilla JS     |
| Vector Database  | Pinecone (Serverless)     |
| Embeddings       | BAAI/bge-small-en-v1.5    |
| LLM              | Groq — Llama 3.3 70B     |
| PDF Processing   | PyPDF                     |

---

## Setup

### 1. Clone and navigate

```bash
cd ai_based_eda_assistant
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file and fill in your keys:

```bash
copy .env.example .env
```

Edit `.env`:

```
GROQ_API_KEY=your_groq_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=eda-assistant
```

**Getting API keys:**

- **Groq** → [console.groq.com](https://console.groq.com) (free tier available)
- **Pinecone** → [app.pinecone.io](https://app.pinecone.io) (free Starter plan)

### 5. Run the application

```bash
uvicorn app:app --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## Usage

1. **Upload** a PDF report (annual report, financial report, placement report, etc.)
2. **Ask** analytical questions in the input box
3. **Review** the AI-generated analysis with source page references

### Example Questions

- Which department performed the best?
- Compare revenue between 2023 and 2024.
- Summarize placement statistics.
- What are the key findings?
- Which KPIs improved?
- Generate an executive summary.
- Identify major risks.

---

## Project Structure

```
├── app.py              # FastAPI backend
├── rag.py              # RAG engine (PDF → chunks → embeddings → LLM)
├── config.py           # Configuration and constants
├── templates/
│   └── index.html      # Frontend HTML
├── static/
│   ├── style.css       # Stylesheet
│   └── script.js       # Frontend logic
├── uploads/            # Uploaded PDFs (auto-created)
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
└── README.md           # This file
```

---

## Notes

- Only **one PDF** is indexed at a time. Uploading a new document replaces the previous one.
- The assistant only answers from the uploaded document. If the answer isn't in the document, it will say so.
- The free Groq tier has rate limits — allow a few seconds between questions if you hit a limit.
