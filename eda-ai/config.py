"""
Configuration — loads environment variables, validates startup requirements, and defines global parameters.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ── API Keys & Validation ─────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "eda-assistant")

def validate_config():
    """Verify that mandatory API keys are present."""
    missing = []
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key":
        missing.append("GROQ_API_KEY")
    if not PINECONE_API_KEY or PINECONE_API_KEY == "your_pinecone_api_key":
        missing.append("PINECONE_API_KEY")
    
    if missing:
        print(f"[WARNING] Missing environment variables: {', '.join(missing)}. Ensure they are set in your .env file.")

# ── Models ────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384
LLM_MODEL = "llama-3.3-70b-versatile"

# ── Chunking & Retrieval Parameters ──────────────────────────────────
CHUNK_SIZE = 600       # Target characters per chunk
CHUNK_OVERLAP = 80     # Overlap between chunks
TOP_K = 5              # Number of chunks retrieved per query
SIMILARITY_THRESHOLD = 0.35 # Score threshold below which context is ignored

# ── Constraints & Memory ──────────────────────────────────────────────
MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_ZIP_FILES = 15     # Maximum files extracted per ZIP archive
MEMORY_TURNS = 4       # Number of prior Q&A turns to retain per doc session

SUPPORTED_DOC_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg"
}
SUPPORTED_EXTENSIONS = SUPPORTED_DOC_EXTENSIONS.union({".zip"})

# ── Paths & Storage ───────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
DB_PATH = os.path.join(BASE_DIR, "eda_assistant.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Run initial validation
validate_config()
