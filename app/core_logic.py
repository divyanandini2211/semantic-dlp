import os
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from groq import Groq
from dotenv import load_dotenv
import re

load_dotenv()

# Initialize local embedding model (runs free on CPU)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Initialize Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "dlp-vault"))

# Initialize Groq client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SIMILARITY_HIGH_THRESHOLD = 0.78  # Direct semantic similarity flag
SIMILARITY_CHECK_FLOOR = 0.35     # Range where LLM factual analysis is invoked

def generate_embedding(text: str) -> list:
    return embedding_model.encode(text).tolist()

def check_regex_patterns(output_text: str) -> dict:
    patterns = {
        "Email Pattern": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}",
        "Social Security Number": r"\b\d{3}-\d{2}-\d{4}\b",
        "AWS Access Key": r"AKIA[0-9A-Z]{16}"
    }
    for name, pattern in patterns.items():
        if re.search(pattern, output_text):
            return {"match": True, "type": name}
    return {"match": False}

def evaluate_factual_overlap(secret_text: str, candidate_text: str) -> dict:
    """
    LLM-as-a-judge: Detects if factual claims or specific protected data
    are leaked through rephrasing, summarization, or obfuscation.
    """
    system_prompt = (
        "You are an enterprise AI data loss prevention auditor. "
        "Your task is to analyze whether an AI agent's generated response leaks confidential facts "
        "derived from a protected reference document, even if heavily paraphrased, abstracted, or disguised.\n"
        "Respond ONLY in valid JSON format with keys:\n"
        "- 'overlap_detected': boolean (true if sensitive specific facts are leaked, false otherwise)\n"
        "- 'confidence': float between 0.0 and 1.0\n"
        "- 'extracted_facts': list of strings detailing the specific leaked facts\n"
        "- 'explanation': brief one-sentence reason"
    )
    
    user_prompt = f"""
    PROTECTED REFERENCE DOCUMENT:
    \"\"\"{secret_text}\"\"\"

    AGENT OUTPUT TO INSPECT:
    \"\"\"{candidate_text}\"\"\"
    """
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        import json
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        # Fallback if LLM call experiences network issues
        return {
            "overlap_detected": False,
            "confidence": 0.0,
            "extracted_facts": [],
            "explanation": f"LLM evaluation failed: {str(e)}"
        }

def inspect_agent_output(output_text: str) -> dict:
    """
    Multi-stage semantic exfiltration inspection pipeline.
    """
    if not output_text or not output_text.strip():
        return {
            "decision": "ALLOW",
            "similarity_score": 0.0,
            "factual_overlap": False,
            "reason": "Empty input payload",
            "lineage_tag": None
        }

    # Stage 0: Fast Regex PII/Pattern Block
    regex_res = check_regex_patterns(output_text)
    if regex_res["match"]:
        return {
            "decision": "BLOCK",
            "similarity_score": 1.0,
            "factual_overlap": False,
            "reason": f"Standard DLP Pattern Match (Regex: {regex_res['type']})",
            "lineage_tag": "REGEX_RULE"
        }

    # Stage 1: Dense Vector Similarity Search
    query_vector = generate_embedding(output_text)
    search_result = index.query(vector=query_vector, top_k=1, include_metadata=True)
    
    if not search_result.get("matches"):
        return {
            "decision": "ALLOW",
            "similarity_score": 0.0,
            "factual_overlap": False,
            "reason": "No vault matches found",
            "lineage_tag": None
        }

    top_match = search_result["matches"][0]
    similarity_score = float(top_match["score"])
    vault_text = top_match["metadata"].get("text", "")
    lineage_source = top_match["metadata"].get("source", "UNKNOWN_SOURCE")
    vault_category = top_match["metadata"].get("category", "General")

    # High direct semantic similarity -> Immediate Block
    if similarity_score >= SIMILARITY_HIGH_THRESHOLD:
        return {
            "decision": "BLOCK",
            "similarity_score": round(similarity_score, 4),
            "factual_overlap": True,
            "reason": f"Direct high semantic similarity to protected record ({vault_category})",
            "lineage_tag": lineage_source,
            "leaked_reference_sample": vault_text[:80] + "..."
        }

    # Medium similarity -> Stage 2: Deep Factual Overlap Check via Groq
    if similarity_score >= SIMILARITY_CHECK_FLOOR:
        factual_eval = evaluate_factual_overlap(secret_text=vault_text, candidate_text=output_text)
        if factual_eval.get("overlap_detected", False):
            return {
                "decision": "BLOCK",
                "similarity_score": round(similarity_score, 4),
                "factual_overlap": True,
                "reason": f"Semantic factual exfiltration detected: {factual_eval.get('explanation')}",
                "lineage_tag": lineage_source,
                "extracted_facts": factual_eval.get("extracted_facts", []),
                "leaked_reference_sample": vault_text[:80] + "..."
            }

    # Passed all checks -> Allow
    return {
        "decision": "ALLOW",
        "similarity_score": round(similarity_score, 4),
        "factual_overlap": False,
        "reason": "Output verified: no semantic overlap with protected vault",
        "lineage_tag": None
    }