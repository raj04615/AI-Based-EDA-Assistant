"""
Database Layer — SQLite registry for document metadata, ingestion status, and conversational session history.
"""

import sqlite3
import os
from typing import List, Dict, Optional, Any
import config

def get_db_connection():
    """Create a thread-safe connection to SQLite database."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables if they do not exist."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Documents Registry Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'pdf',
                page_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'processing',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Safely migrate existing databases missing file_type or markdown_path columns
        cursor.execute("PRAGMA table_info(documents)")
        columns = [col["name"] for col in cursor.fetchall()]
        if "file_type" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN file_type TEXT NOT NULL DEFAULT 'pdf'")
        if "markdown_path" not in columns:
            cursor.execute("ALTER TABLE documents ADD COLUMN markdown_path TEXT")
        
        # Chat History Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()

# Ensure DB initialization on module load
init_db()

# ── Document CRUD Operations ──────────────────────────────────────────

def create_document(doc_id: str, filename: str, file_size: int, file_type: str = "pdf") -> Dict[str, Any]:
    """Register a new document with 'processing' status."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO documents (doc_id, filename, file_size, file_type, status)
            VALUES (?, ?, ?, ?, 'processing')
        """, (doc_id, filename, file_size, file_type))
        conn.commit()
    return get_document(doc_id)

def update_document_status(
    doc_id: str,
    status: str,
    page_count: Optional[int] = None,
    chunk_count: Optional[int] = None,
    error_message: Optional[str] = None,
    markdown_path: Optional[str] = None
):
    """Update document ingestion status and stats."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        updates = ["status = ?"]
        params = [status]
        
        if page_count is not None:
            updates.append("page_count = ?")
            params.append(page_count)
            
        if chunk_count is not None:
            updates.append("chunk_count = ?")
            params.append(chunk_count)
            
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        if markdown_path is not None:
            updates.append("markdown_path = ?")
            params.append(markdown_path)
            
        params.append(doc_id)
        query = f"UPDATE documents SET {', '.join(updates)} WHERE doc_id = ?"
        cursor.execute(query, tuple(params))
        conn.commit()

def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve document details by doc_id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def list_documents() -> List[Dict[str, Any]]:
    """Retrieve all registered documents sorted by upload date descending."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_document(doc_id: str) -> bool:
    """Delete document and its chat history from SQLite."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_history WHERE doc_id = ?", (doc_id,))
        cursor.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        conn.commit()
        return cursor.rowcount > 0

# ── Chat History Operations ───────────────────────────────────────────

def add_chat_turn(doc_id: str, question: str, answer: str):
    """Record a Q&A exchange for a document session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_history (doc_id, question, answer)
            VALUES (?, ?, ?)
        """, (doc_id, question, answer))
        conn.commit()

def get_recent_chat_history(doc_id: str, limit: int = config.MEMORY_TURNS) -> List[Dict[str, str]]:
    """Fetch recent Q&A turns for inclusion in LLM prompt context."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT question, answer FROM chat_history
            WHERE doc_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (doc_id, limit))
        rows = cursor.fetchall()
        # Return in chronological order
        return [{"question": row["question"], "answer": row["answer"]} for row in reversed(rows)]
