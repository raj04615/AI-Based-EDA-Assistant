"""
Pytest Suite for Markdown Normalization, Canonical Markdown Chunking, and Endpoint Verification.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

import database
import ingestion
import config
from app import app

client = TestClient(app)


def test_normalize_to_markdown_front_matter_and_headings():
    """Verify YAML front matter and section headings across different formats."""
    doc_id = "test-norm-1"
    filename = "quarterly_report.pdf"
    
    extracted_content = [
        {
            "page": 1,
            "page_label": "Page 1",
            "text": "Executive summary of revenue growth.",
            "tables": ["| Department | Growth |\n| --- | --- |\n| Cloud | +35% |"]
        },
        {
            "page": 2,
            "page_label": "Page 2",
            "text": "* Point 1: Cloud adoption\n* Point 2: Cost efficiency",
            "tables": []
        }
    ]

    md_output = ingestion.normalize_to_markdown(extracted_content, "pdf", filename, doc_id)
    
    # Check Front Matter
    assert "---" in md_output
    assert f"title: {filename}" in md_output
    assert f"doc_id: {doc_id}" in md_output
    assert "file_type: pdf" in md_output
    assert "page_count: 2" in md_output
    assert "ingested_at:" in md_output

    # Check Headings & Tables
    assert "## Page 1" in md_output
    assert "## Page 2" in md_output
    assert "| Department | Growth |" in md_output

    # Check Lists
    assert "* Point 1: Cloud adoption" in md_output
    assert "* Point 2: Cost efficiency" in md_output


def test_normalize_to_markdown_pptx_and_csv():
    """Test PPTX slide_count and CSV row_count normalization."""
    # PPTX test
    pptx_content = [
        {"page": 1, "page_label": "Slide 1", "text": "Slide 1 Content", "tables": []},
        {"page": 2, "page_label": "Slide 2", "text": "Slide 2 Content", "tables": []}
    ]
    pptx_md = ingestion.normalize_to_markdown(pptx_content, "pptx", "presentation.pptx", "doc-pptx")
    assert "slide_count: 2" in pptx_md
    assert "## Slide 1" in pptx_md

    # CSV test
    csv_content = [
        {
            "page": 1,
            "page_label": "Sheet 'Data' (Rows 1-50)",
            "text": "Data excerpt:",
            "tables": ["| ID | Name |\n| --- | --- |\n| 101 | Alice |\n| 102 | Bob |"]
        }
    ]
    csv_md = ingestion.normalize_to_markdown(csv_content, "csv", "data.csv", "doc-csv")
    assert "row_count: 2" in csv_md
    assert "## Sheet 'Data'" in csv_md


def test_normalize_to_markdown_image_ocr():
    """Test Image OCR section wrapper."""
    ocr_content = [
        {"page": 1, "page_label": "Image 1", "text": "Invoice #9921 Total: $450", "tables": []}
    ]
    img_md = ingestion.normalize_to_markdown(ocr_content, "image", "receipt.png", "doc-img")
    assert "## Extracted Text (OCR)" in img_md
    assert "Invoice #9921" in img_md


def test_chunk_markdown():
    """Verify sentence-aware chunker operating directly on Markdown string."""
    sample_md = """---
title: test.pdf
source_filename: test.pdf
file_type: pdf
doc_id: test-123
ingested_at: 2026-08-12T00:00:00Z
page_count: 2
---

## Page 1

First section sentence one. First section sentence two. First section sentence three.

| Metric | Value |
| --- | --- |
| ARR | $50M |

## Page 2

Second section narrative content explaining key performance metrics.
"""

    chunks = ingestion.chunk_markdown(sample_md, chunk_size=200)
    assert len(chunks) >= 2

    # Verify table chunk
    table_chunks = [c for c in chunks if c.get("is_table")]
    assert len(table_chunks) == 1
    assert "ARR" in table_chunks[0]["text"]
    assert table_chunks[0]["page_labels"] == ["Page 1"]

    # Verify narrative chunks
    text_chunks = [c for c in chunks if not c.get("is_table")]
    assert any("First section" in c["text"] for c in text_chunks)
    assert any("Second section" in c["text"] for c in text_chunks)


def test_get_document_markdown_api():
    """Test GET /document/{doc_id}/markdown endpoint."""
    test_doc_id = "test-md-endpoint-doc"
    filename = "report.pdf"

    # Register test doc in DB
    database.create_document(test_doc_id, filename, file_size=2048, file_type="pdf")

    # Create dummy processed markdown file
    md_content = "---\ntitle: report.pdf\n---\n\n## Page 1\n\nSample content."
    processed_file = os.path.join(config.PROCESSED_DIR, f"{test_doc_id}.md")
    with open(processed_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    database.update_document_status(test_doc_id, "ready", markdown_path=processed_file)

    try:
        # 1. Fetch via primary route /document/{doc_id}/markdown
        response = client.get(f"/document/{test_doc_id}/markdown")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "Sample content." in response.text

        # 2. Fetch via plural route alias /documents/{doc_id}/markdown
        response_plural = client.get(f"/documents/{test_doc_id}/markdown")
        assert response_plural.status_code == 200
        assert "Sample content." in response_plural.text

    finally:
        # Clean up
        if os.path.exists(processed_file):
            os.remove(processed_file)
        database.delete_document(test_doc_id)


def test_legacy_document_markdown_404():
    """Test that legacy documents without markdown files return 404 gracefully."""
    legacy_doc_id = "legacy-doc-999"
    database.create_document(legacy_doc_id, "old_doc.pdf", file_size=1000)

    try:
        response = client.get(f"/document/{legacy_doc_id}/markdown")
        assert response.status_code == 404
        assert "Markdown representation not available" in response.json()["detail"]
    finally:
        database.delete_document(legacy_doc_id)
