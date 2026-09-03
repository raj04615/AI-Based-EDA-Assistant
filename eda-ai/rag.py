"""
RAG Engine — Modular interface mapping ingestion, retrieval, and database functions.
"""

import database
import ingestion
import retrieval

# Re-export key pipeline functions for modular access
run_ingestion_pipeline = ingestion.run_ingestion_pipeline
retrieve_chunks = retrieval.retrieve_chunks
generate_answer_stream = retrieval.generate_answer_stream
get_recent_chat_history = database.get_recent_chat_history
