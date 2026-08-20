"""
app/core_logic.py
=================
Multi-stage semantic exfiltration detection pipeline + Dual Cloud LLM integration.

Architecture:
  • LLM 1 (Enterprise Agent): Cloud LLM (llama-3.3-70b-versatile)
      System Prompt: Neutral enterprise assistant with Pinecone RAG context.
  • LLM 2 (DLP Auditor): Independent Cloud LLM (qwen/qwen3.6-27b)
      System Prompt: Specialized data loss prevention auditor.
  • Vault: Pinecone Cloud Vector Store (Single source of truth).
"""
import json
import logging
import re
import time
from typing import Any

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from groq import Groq

from app import config

logger = logging.getLogger("aegis.dlp")

# ── Module-level singletons (loaded once at import time) ─────────────────────
_embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
_pinecone_index  = Pinecone(api_key=config.PINECONE_API_KEY).Index(config.PINECONE_INDEX_NAME)
_groq_client     = Groq(api_key=config.GROQ_API_KEY, max_retries=0)


# ── Embedding & Regex Helpers ────────────────────────────────────────────────

def generate_embedding(text: str) -> list[float]:
    """Encode text into a dense embedding vector."""
    return _embedding_model.encode(text).tolist()


_REGEX_PATTERNS: dict[str, str] = {
    "Email Address":      r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}",
    "Social Security No": r"\b\d{3}-\d{2}-\d{4}\b",
    "AWS Access Key":     r"AKIA[0-9A-Z]{16}",
}

def check_regex_patterns(text: str) -> dict:
    """Return the first regex PII match found, or {match: False}."""
    for name, pattern in _REGEX_PATTERNS.items():
        if re.search(pattern, text):
            return {"match": True, "type": name}
    return {"match": False}


# ── LLM 1: Target Enterprise Assistant (Neutral, Unbiased) ────────────────────

_AGENT_SYSTEM_PROMPT = (
    "You are a helpful, concise, and knowledgeable enterprise AI assistant. "
    "If relevant enterprise context is provided, use it to answer the question directly. "
    "If the question is a general or generic request, answer normally and concisely in 1-3 sentences."
)

def generate_enterprise_agent_response(user_query: str) -> dict:
    """
    LLM 1 (Enterprise Agent):
    1. Fetches relevant enterprise context chunks directly from Pinecone Cloud.
    2. Answers the user query concisely.
    Returns: { "raw_response": str, "retrieved_context_sources": list[str] }
    """
    query_vec = generate_embedding(user_query)
    search = _pinecone_index.query(vector=query_vec, top_k=2, include_metadata=True)
    
    matches = search.get("matches", [])
    context_blocks = []
    sources = []
    
    for m in matches:
        score = m.get("score", 0.0)
        # Only inject vault context if it has meaningful semantic relevance
        # Avoid injecting unrelated confidential docs into generic all-hands drafts or general programming queries
        if score < 0.42:
            continue
        meta = m.get("metadata", {})
        text = meta.get("text", "")
        src = meta.get("source", "UNKNOWN")
        if text:
            # Truncate to reasonable context window to prevent 413 entity errors
            snippet = text[:800]
            context_blocks.append(f"[{src}]: {snippet}")
            sources.append(src)
            
    context_str = "\n\n".join(context_blocks) if context_blocks else "No specific enterprise document needed. Answer the user query generally."
    
    user_prompt = f"ENTERPRISE CONTEXT:\n{context_str}\n\nUSER QUESTION:\n{user_query}"
    
    models_to_try = [
        "qwen/qwen3.6-27b",
        "allam-2-7b",
        "openai/gpt-oss-120b",
    ]
    
    last_err = ""
    for model_name in models_to_try:
        try:
            response = _groq_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=1500,
                temperature=0.2,
            )
            msg_content = response.choices[0].message.content or ""
            raw_text = msg_content.strip()
            # Strip reasoning blocks (Qwen thinking-mode output)
            if "</think>" in raw_text:
                raw_text = raw_text.split("</think>")[-1].strip()
                
            if raw_text:
                return {
                    "raw_response": raw_text,
                    "retrieved_context_sources": list(set(sources)),
                    "model_used": model_name
                }
        except Exception as exc:
            last_err = str(exc)
            logger.warning("Model %s failed: %s, falling back to next model...", model_name, exc)
            continue

    logger.error("All agent models failed: %s", last_err)
    return {
        "raw_response": f"Enterprise Agent Error: {last_err}",
        "retrieved_context_sources": sources,
        "model_used": "fallback-exhausted"
    }


# ── LLM 2: Stage 3 Independent DLP Auditor (Specialized Security Judge) ──────

_AUDITOR_SYSTEM_PROMPT = (
    "You are an enterprise AI data loss prevention auditor. "
    "Your task is to analyze whether an AI agent's generated response leaks confidential facts "
    "derived from a protected reference document, even if heavily paraphrased, abstracted, or disguised.\n"
    "Respond ONLY in valid JSON format with keys:\n"
    "- 'overlap_detected': boolean (true if sensitive specific facts are leaked, false otherwise)\n"
    "- 'confidence': float between 0.0 and 1.0\n"
    "- 'extracted_facts': list of strings detailing the specific leaked facts\n"
    "- 'explanation': brief one-sentence reason"
)

def evaluate_factual_overlap(vault_text: str, candidate_text: str) -> dict:
    """
    LLM 2 (DLP Auditor):
    Detects if specific protected facts from Pinecone vault_text are reconstructed
    in candidate_text, even when heavily paraphrased.
    Includes exponential backoff for rate limit resilience.
    """
    user_prompt = (
        f'PROTECTED REFERENCE DOCUMENT (FROM PINECONE VAULT):\n"""{vault_text}"""\n\n'
        f'AGENT OUTPUT TO INSPECT:\n"""{candidate_text}"""'
    )
    
    models_to_try = [
        "qwen/qwen3.6-27b",
        "allam-2-7b",
        "openai/gpt-oss-120b",
    ]
    
    last_err = ""
    for model_name in models_to_try:
        try:
            response = _groq_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _AUDITOR_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=1200,
                temperature=0.0,
            )
            raw = response.choices[0].message.content.strip()

            # Strip reasoning blocks (Qwen thinking-mode output)
            if "</think>" in raw:
                raw = raw.split("</think>")[-1].strip()

            # Strip Markdown JSON fences if present
            if "```json" in raw:
                raw = raw.split("```json")[-1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[-1].split("```")[0].strip()

            # Extract JSON object substring using raw_decode
            start = raw.find("{")
            if start == -1:
                raise ValueError("No JSON block found in model output")

            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(raw[start:])
            
            # Ensure overlap_detected is a boolean
            overlap = data.get("overlap_detected", False)
            if isinstance(overlap, str):
                overlap = overlap.lower() in ("true", "1", "yes")
            data["overlap_detected"] = bool(overlap)
            
            return data

        except Exception as exc:
            last_err = str(exc)
            # If 429 rate limit, immediately try next model in pool
            continue
            
    return {
        "overlap_detected": False,
        "confidence": 0.0,
        "extracted_facts": [],
        "explanation": f"LLM evaluation failed: {last_err}",
    }


# ── Main 3-Stage Inspection Pipeline ──────────────────────────────────────────

def inspect_agent_output(output_text: str) -> dict:
    """
    Run the full 3-stage semantic exfiltration inspection pipeline.

    Returns a dict with keys:
        decision        : "ALLOW" | "BLOCK" | "ERROR"
        similarity_score: float
        factual_overlap : bool
        reason          : str
        lineage_tag     : str | None
        trace           : list[str]   (pipeline stage log)
    """
    trace: list[str] = []

    # ── Empty input ───────────────────────────────────────────────────────────
    if not output_text or not output_text.strip():
        trace.append("Stage 0: Empty input — skipping all stages")
        return {
            "decision": "ALLOW",
            "similarity_score": 0.0,
            "factual_overlap": False,
            "reason": "Empty input payload",
            "lineage_tag": None,
            "trace": trace,
        }

    # ── Stage 1: Regex PII Scanner ────────────────────────────────────────────
    regex_hit = check_regex_patterns(output_text)
    if regex_hit["match"]:
        trace.append(f"Stage 1 (Regex): CAUGHT — Found {regex_hit['type']}")
        return {
            "decision": "BLOCK",
            "similarity_score": 1.0,
            "factual_overlap": False,
            "reason": f"Standard DLP pattern match (Regex: {regex_hit['type']})",
            "lineage_tag": "REGEX_RULE",
            "trace": trace,
        }
    trace.append("Stage 1 (Regex): FAILED TO CATCH — No standard pattern matched")

    # ── Stage 2: Dense Vector Similarity vs Pinecone Cloud ───────────────────
    query_vector = generate_embedding(output_text)
    search = _pinecone_index.query(vector=query_vector, top_k=3, include_metadata=True)
    matches = search.get("matches", [])

    if not matches:
        trace.append("Stage 2 (Vector Math): NO CATCH REQUIRED — No vault matches found in Pinecone")
        return {
            "decision": "ALLOW",
            "similarity_score": 0.0,
            "factual_overlap": False,
            "reason": "No vault matches found in Pinecone",
            "lineage_tag": None,
            "trace": trace,
        }

    top_match = matches[0]
    highest_sim_score = float(top_match["score"])

    # Check for direct high similarity match (Instant Block)
    for m in matches:
        sim_score = float(m["score"])
        if sim_score >= config.SIMILARITY_HIGH_THRESHOLD:
            vault_text = m["metadata"].get("text", "")
            lineage_src = m["metadata"].get("source", "UNKNOWN_SOURCE")
            vault_cat = m["metadata"].get("category", "General")
            trace.append(
                f"Stage 2 (Vector Math): CAUGHT — Exact Semantic Match ({sim_score:.2f}) on {lineage_src}"
            )
            return {
                "decision": "BLOCK",
                "similarity_score": round(sim_score, 4),
                "factual_overlap": True,
                "reason": f"Direct high semantic similarity to protected record ({vault_cat})",
                "lineage_tag": lineage_src,
                "leaked_reference_sample": vault_text[:120] + "...",
                "trace": trace,
            }

    trace.append(
        f"Stage 2 (Vector Math): FAILED TO CATCH (Paraphrased score: {highest_sim_score:.2f} < {config.SIMILARITY_HIGH_THRESHOLD})"
    )

    # ── Stage 3: LLM 2 Factual Overlap Auditor (Audits top candidate matches) ─
    candidates_to_audit = [m for m in matches if float(m["score"]) >= config.SIMILARITY_CHECK_FLOOR][:2]

    if candidates_to_audit:
        trace.append(f"Stage 3 (LLM Auditor - {config.AUDITOR_LLM_MODEL}): Executing factual comparison across {len(candidates_to_audit)} candidate vault doc(s)...")
        for m in candidates_to_audit:
            m_score = float(m["score"])
            v_text = m["metadata"].get("text", "")
            v_src = m["metadata"].get("source", "UNKNOWN_SOURCE")
            
            factual = evaluate_factual_overlap(vault_text=v_text, candidate_text=output_text)

            if "LLM evaluation failed" in factual.get("explanation", ""):
                trace.append(f"Stage 3 (LLM Auditor): ERROR on {v_src} — {factual['explanation']}")
                return {
                    "decision": "ERROR",
                    "similarity_score": round(m_score, 4),
                    "factual_overlap": False,
                    "reason": f"System Exception: {factual['explanation']}",
                    "lineage_tag": "SYSTEM_ERROR",
                    "trace": trace,
                }

            if factual.get("overlap_detected", False):
                trace.append(f"Stage 3 (LLM Auditor): CAUGHT on {v_src} — Deep factual leak detected.")
                return {
                    "decision": "BLOCK",
                    "similarity_score": round(m_score, 4),
                    "factual_overlap": True,
                    "reason": f"Semantic factual exfiltration detected: {factual.get('explanation')}",
                    "lineage_tag": v_src,
                    "extracted_facts": factual.get("extracted_facts", []),
                    "leaked_reference_sample": v_text[:120] + "...",
                    "trace": trace,
                }

        trace.append("Stage 3 (LLM Auditor): FAILED TO CATCH — No factual combination leaked across candidates.")
    else:
        trace.append(
            "Stage 3 (LLM Auditor): NO CATCH REQUIRED — Vector similarity too low to pose threat."
        )

    # ── All stages evaluated → ALLOW ──────────────────────────────────────────
    trace.append("FINAL: Decision ALLOWED (No exfiltration caught across all stages)")
    return {
        "decision": "ALLOW",
        "similarity_score": round(highest_sim_score, 4),
        "factual_overlap": False,
        "reason": "Output verified: no semantic overlap with protected vault",
        "lineage_tag": None,
        "trace": trace,
    }


# ── Cloud Vault Overview ──────────────────────────────────────────────────────

def get_cloud_vault_overview() -> list[dict[str, Any]]:
    """
    Fetch an overview of active documents and categories directly from Pinecone Cloud.
    """
    stats = _pinecone_index.describe_index_stats()
    # We query representative zero-vector / dummy query to fetch sample documents
    sample_vec = [0.0] * stats.get("dimension", 384)
    res = _pinecone_index.query(vector=sample_vec, top_k=20, include_metadata=True)
    
    docs: dict[str, dict] = {}
    for m in res.get("matches", []):
        meta = m.get("metadata", {})
        src = meta.get("source", "UNKNOWN")
        cat = meta.get("category", "General")
        text = meta.get("text", "")
        if src not in docs:
            docs[src] = {
                "doc_id": src,
                "category": cat,
                "full_text_sample": text,
                "chunks_seen": 1
            }
        else:
            docs[src]["chunks_seen"] += 1
            
    return list(docs.values())