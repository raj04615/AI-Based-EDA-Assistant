"""
Retrieval Engine — Namespaced vector search, similarity thresholding, session memory, tenacity retries, and SSE streaming.
"""

import json
import traceback
from typing import List, Dict, Any, AsyncGenerator
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from pinecone import Pinecone
from groq import Groq

import config
import database
import ingestion

_pinecone_index = None
_groq_client = None

def get_pinecone_index():
    """Lazy initialization of Pinecone index handle."""
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=config.PINECONE_API_KEY)
        _pinecone_index = pc.Index(config.PINECONE_INDEX_NAME)
    return _pinecone_index

def get_groq_client() -> Groq:
    """Lazy initialization of Groq API client."""
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client

# ── Tenacity Retry-Protected Operations ───────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True
)
def query_pinecone_namespace(query_vector: List[float], doc_id: str, top_k: int = config.TOP_K):
    """Query Pinecone vector database under namespace=doc_id with automatic retries."""
    index = get_pinecone_index()
    return index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=doc_id,
        include_metadata=True
    )


def retrieve_chunks(doc_id: str, question: str) -> List[Dict[str, Any]]:
    """
    Embed question, query Pinecone namespace, and filter out low-confidence chunks.
    """
    embedder = ingestion.get_embedding_model()
    q_vector = embedder.encode([question], normalize_embeddings=True)[0].tolist()
    
    response = query_pinecone_namespace(q_vector, doc_id)
    matches = response.get("matches", [])
    
    retrieved_chunks = []
    for m in matches:
        score = m.get("score", 0.0)
        metadata = m.get("metadata", {})
        
        # Apply similarity threshold
        if score >= config.SIMILARITY_THRESHOLD:
            # Parse page numbers or unit labels from metadata
            raw_pages = metadata.get("pages", [])
            pages = []
            for p in raw_pages:
                sp = str(p)
                if sp.isdigit():
                    pages.append(f"Page {sp}")
                else:
                    pages.append(sp)
            
            retrieved_chunks.append({
                "text": metadata.get("text", ""),
                "pages": sorted(list(set(pages))),
                "score": round(score, 4),
                "is_table": metadata.get("is_table", False)
            })
            
    return retrieved_chunks


def build_prompt_messages(question: str, chunks: List[Dict[str, Any]], chat_history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Construct chat messages prompt incorporating context, session history, and page/slide/row citation rules.
    """
    system_prompt = (
        "You are an expert AI Data Analyst specializing in organizational, financial, and analytical report processing.\n"
        "Your task is to provide accurate, concise, data-driven answers to user queries based ONLY on the provided context excerpts.\n\n"
        "STRICT GUIDELINES:\n"
        "1. Base your answer strictly on the provided Context. Do NOT use outside knowledge.\n"
        "2. If the context does not contain enough information to answer the question, state: "
        "'I could not find sufficient information in the document to answer this question.'\n"
        "3. Always cite exact page, slide, sheet, or row references inline when stating metrics, figures, or key facts (e.g. '[Page 12]', '[Slide 4]', '[Row 15]').\n"
        "4. Format numerical data and analytical tables clearly in Markdown format when appropriate.\n"
        "5. Maintain continuity with previous conversation history if the user asks a follow-up question."
    )

    messages = [{"role": "system", "content": system_prompt}]

    # Include recent conversation memory
    if chat_history:
        for turn in chat_history:
            messages.append({"role": "user", "content": turn["question"]})
            messages.append({"role": "assistant", "content": turn["answer"]})

    # Build context string with unit tags
    context_str = ""
    for i, c in enumerate(chunks, start=1):
        pages_str = ", ".join(c["pages"])
        context_str += f"\n--- EXCERPT {i} [{pages_str}] ---\n{c['text']}\n"

    user_message = f"DOCUMENT CONTEXT:\n{context_str}\n\nUSER QUESTION:\n{question}"
    messages.append({"role": "user", "content": user_message})

    return messages


async def generate_answer_stream(doc_id: str, question: str) -> AsyncGenerator[str, None]:
    """
    Stream answer tokens via SSE format and append resulting turn into chat history.
    """
    try:
        # Retrieve chunks with score thresholding
        chunks = retrieve_chunks(doc_id, question)

        if not chunks:
            fallback_msg = "Information not found in the uploaded document."
            yield f"data: {json.dumps({'token': fallback_msg})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
            database.add_chat_turn(doc_id, question, fallback_msg)
            return

        # Prepare source page metadata for frontend display
        sources = []
        for c in chunks:
            sources.append({
                "pages": c["pages"],
                "text": c["text"],
                "score": c["score"],
                "is_table": c["is_table"]
            })

        # Fetch recent session memory (up to MEMORY_TURNS)
        chat_history = database.get_recent_chat_history(doc_id)
        messages = build_prompt_messages(question, chunks, chat_history)

        # Call Groq API with streaming
        client = get_groq_client()
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
            stream=True
        )

        full_answer = ""
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                full_answer += delta
                yield f"data: {json.dumps({'token': delta})}\n\n"

        # Signal completion with sources payload
        yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"

        # Save to chat history SQLite
        database.add_chat_turn(doc_id, question, full_answer)

    except Exception as e:
        error_msg = f"An error occurred while generating the answer: {str(e)}"
        print(f"[RETRIEVAL ERROR] {error_msg}")
        traceback.print_exc()
        yield f"data: {json.dumps({'error': error_msg})}\n\n"
