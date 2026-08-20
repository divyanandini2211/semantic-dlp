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
            model="qwen/qwen3.6-27b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        import json
        raw_output = response.choices[0].message.content.strip()
        
        # Qwen prints reasoning steps in <think> tags. Strip them out.
        if "</think>" in raw_output:
            raw_output = raw_output.split("</think>")[-1].strip()
        
        # Remove Markdown JSON formatting if the model wrapped it
        if "```json" in raw_output:
            raw_output = raw_output.split("```json")[-1]
            raw_output = raw_output.split("```")[0].strip()
        
        return json.loads(raw_output)
    except Exception as e:
        # Fallback if LLM call experiences network/quota issues
        error_msg = str(e)
        if "429" in error_msg or "rate limit" in error_msg.lower():
            explanation = "LLM evaluation failed: API Credit / Rate Limit exceeded."
        else:
            explanation = f"LLM evaluation failed: {error_msg}"
            
        return {
            "overlap_detected": False,
            "confidence": 0.0,
            "extracted_facts": [],
            "explanation": explanation
        }

def inspect_agent_output(output_text: str) -> dict:
    """
    Multi-stage semantic exfiltration inspection pipeline.
    """
    pipeline_trace = []
    
    if not output_text or not output_text.strip():
        pipeline_trace.append("Stage 0: Input Empty")
        return {
            "decision": "ALLOW",
            "similarity_score": 0.0,
            "factual_overlap": False,
            "reason": "Empty input payload",
            "lineage_tag": None,
            "trace": pipeline_trace
        }

    # Stage 0: Fast Regex PII/Pattern Block
    regex_res = check_regex_patterns(output_text)
    if regex_res["match"]:
        pipeline_trace.append(f"Stage 1 (Regex): BLOCKED - Found {regex_res['type']}")
        return {
            "decision": "BLOCK",
            "similarity_score": 1.0,
            "factual_overlap": False,
            "reason": f"Standard DLP Pattern Match (Regex: {regex_res['type']})",
            "lineage_tag": "REGEX_RULE",
            "trace": pipeline_trace
        }
    pipeline_trace.append("Stage 1 (Regex): PASSED - No PII matched")

    # Stage 1: Dense Vector Similarity Search
    query_vector = generate_embedding(output_text)
    search_result = index.query(vector=query_vector, top_k=1, include_metadata=True)
    
    if not search_result.get("matches"):
        pipeline_trace.append("Stage 2 (Vector Math): PASSED - No vault matches found")
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
        pipeline_trace.append(f"Stage 2 (Vector Math): BLOCKED - Exact Semantic Match ({similarity_score:.2f})")
        return {
            "decision": "BLOCK",
            "similarity_score": round(similarity_score, 4),
            "factual_overlap": True,
            "reason": f"Direct high semantic similarity to protected record ({vault_category})",
            "lineage_tag": lineage_source,
            "leaked_reference_sample": vault_text[:80] + "...",
            "trace": pipeline_trace
        }
    
    pipeline_trace.append(f"Stage 2 (Vector Math): PASSED (Score: {similarity_score:.2f} < {SIMILARITY_HIGH_THRESHOLD})")

    # Medium similarity -> Stage 2: Deep Factual Overlap Check via Groq
    if similarity_score >= SIMILARITY_CHECK_FLOOR:
        pipeline_trace.append("Stage 3 (LLM Auditor): Executing factual comparison...")
        factual_eval = evaluate_factual_overlap(secret_text=vault_text, candidate_text=output_text)
        
        if "LLM evaluation failed" in factual_eval.get("explanation", ""):
            pipeline_trace.append(f"Stage 3 (LLM Auditor): ERROR - {factual_eval.get('explanation')}")
            pipeline_trace.append("FINAL: Decision ERROR (Fail-Closed due to API outage)")
            return {
                "decision": "ERROR",
                "similarity_score": round(similarity_score, 4),
                "factual_overlap": False,
                "reason": f"System Exception: {factual_eval.get('explanation')}",
                "lineage_tag": "SYSTEM_ERROR",
                "trace": pipeline_trace
            }
        
        if factual_eval.get("overlap_detected", False):
            pipeline_trace.append("Stage 3 (LLM Auditor): BLOCKED - Deep factual leak detected.")
            return {
                "decision": "BLOCK",
                "similarity_score": round(similarity_score, 4),
                "factual_overlap": True,
                "reason": f"Semantic factual exfiltration detected: {factual_eval.get('explanation')}",
                "lineage_tag": lineage_source,
                "extracted_facts": factual_eval.get("extracted_facts", []),
                "leaked_reference_sample": vault_text[:80] + "...",
                "trace": pipeline_trace
            }
        else:
            if not "ERROR" in pipeline_trace[-1]:
                pipeline_trace.append("Stage 3 (LLM Auditor): PASSED - No factual combination leaked.")
    else:
        pipeline_trace.append("Stage 3 (LLM Auditor): SKIPPED - Vector similarity so low it poses no threat.")

    # Passed all checks -> Allow
    pipeline_trace.append("FINAL: Decision ALLOWED")
    return {
        "decision": "ALLOW",
        "similarity_score": round(similarity_score, 4),
        "factual_overlap": False,
        "reason": "Output verified: no semantic overlap with protected vault",
        "lineage_tag": None,
        "trace": pipeline_trace
    }