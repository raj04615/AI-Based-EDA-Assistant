"""
Pytest Unit & Integration Test Suite — Ingestion chunker, database operations, and API endpoints.
"""

import pytest
import database
import ingestion
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_sentence_aware_chunking():
    """Verify that sentence-aware chunking preserves table markdown and page tags."""
    pages_data = [
        {
            "page": 1,
            "text": "Executive summary of corporate report. The annual revenue grew by 15% in Q4. All departments performed well.",
            "tables": ["| Department | Revenue |\n| --- | --- |\n| Engineering | $10M |"]
        }
    ]

    chunks = ingestion.chunk_text_sentence_aware(pages_data, chunk_size=300)
    assert len(chunks) >= 2
    
    # Verify table chunk present
    table_chunks = [c for c in chunks if c.get("is_table")]
    assert len(table_chunks) == 1
    assert "Engineering" in table_chunks[0]["text"]
    assert table_chunks[0]["pages"] == [1]


def test_database_crud_operations():
    """Test SQLite document creation, status updating, and chat history retention."""
    test_doc_id = "test-doc-12345"
    filename = "sample_test_report.pdf"
    
    # 1. Create document
    doc = database.create_document(test_doc_id, filename, file_size=1024)
    assert doc["doc_id"] == test_doc_id
    assert doc["status"] == "processing"
    
    # 2. Update status
    database.update_document_status(test_doc_id, "ready", page_count=5, chunk_count=10)
    updated_doc = database.get_document(test_doc_id)
    assert updated_doc["status"] == "ready"
    assert updated_doc["page_count"] == 5
    assert updated_doc["chunk_count"] == 10
    
    # 3. Add chat history turn
    database.add_chat_turn(test_doc_id, "What is total revenue?", "Total revenue is $10M.")
    history = database.get_recent_chat_history(test_doc_id)
    assert len(history) == 1
    assert history[0]["question"] == "What is total revenue?"
    assert history[0]["answer"] == "Total revenue is $10M."
    
    # 4. Clean up
    deleted = database.delete_document(test_doc_id)
    assert deleted is True
    assert database.get_document(test_doc_id) is None


def test_documents_api_endpoint():
    """Test GET /documents endpoint returns valid list."""
    response = client.get("/documents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_invalid_upload_format():
    """Test POST /upload rejects unsupported binary formats like .exe."""
    files = {"file": ("test.exe", b"\x00\x01\x02\x03\x04\x05", "application/octet-stream")}
    response = client.post("/upload", files=files)
    assert response.status_code == 400
    assert "Unsupported or corrupted" in response.json()["message"]
