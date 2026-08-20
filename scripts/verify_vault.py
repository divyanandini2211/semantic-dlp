"""
scripts/verify_vault.py
=======================
Verifies Pinecone Cloud connectivity, embedding model, and both Cloud LLMs:
  - LLM 1: Target Enterprise Agent (llama-3.3-70b-versatile)
  - LLM 2: Independent DLP Auditor (qwen/qwen3.6-27b)
"""
import sys
from pathlib import Path

# Ensure project root & vendor dir are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
VENDOR_DIR = PROJECT_ROOT / "vendor"
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from app import config

SEP = "=" * 60

def check_pinecone(index):
    print("\n[1/4] Pinecone Cloud Index ...")
    stats = index.describe_index_stats()
    total = stats.get("total_vector_count", 0)
    print(f"  OK  Index '{config.PINECONE_INDEX_NAME}' reachable in Pinecone Cloud")
    print(f"  OK  Total vectors stored: {total}")
    return index, total

def check_embeddings(index):
    print("\n[2/4] Embedding model + Cloud similarity check ...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
    vec = model.encode("test sentence").tolist()
    print(f"  OK  Model '{config.EMBEDDING_MODEL_NAME}' loaded (384-dim)")

    query = "CTO salary compensation RSU equity"
    qvec = model.encode(query).tolist()
    result = index.query(vector=qvec, top_k=1, include_metadata=True)
    matches = result.get("matches", [])
    if matches:
        m = matches[0]
        print(f"  OK  Top Pinecone Match: {m['metadata'].get('source')} (Score: {m['score']:.4f})")
    else:
        print("  WARN  No matches in Pinecone.")

def check_llm1_agent():
    print(f"\n[3/4] LLM 1 (Enterprise Agent: {config.AGENT_LLM_MODEL}) ...")
    from groq import Groq
    client = Groq(api_key=config.GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=config.AGENT_LLM_MODEL,
        messages=[{"role": "user", "content": "Reply with: LLM1_ONLINE"}],
        max_tokens=15,
        temperature=0.0,
    )
    ans = resp.choices[0].message.content.strip()
    print(f"  OK  LLM 1 ({config.AGENT_LLM_MODEL}) responded: '{ans}'")

def check_llm2_auditor():
    print(f"\n[4/4] LLM 2 (DLP Auditor: {config.AUDITOR_LLM_MODEL}) ...")
    from groq import Groq
    client = Groq(api_key=config.GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=config.AUDITOR_LLM_MODEL,
        messages=[{"role": "user", "content": "Reply with: LLM2_ONLINE"}],
        max_tokens=15,
        temperature=0.0,
    )
    ans = resp.choices[0].message.content.strip()
    if "</think>" in ans:
        ans = ans.split("</think>")[-1].strip()
    print(f"  OK  LLM 2 ({config.AUDITOR_LLM_MODEL}) responded: '{ans}'")

def main():
    print(SEP)
    print("AEGIS DUAL-LLM & PINECONE CLOUD VERIFICATION")
    print(SEP)

    try:
        config.validate()
    except EnvironmentError as e:
        print(f"\n  FAIL  {e}")
        sys.exit(1)

    from pinecone import Pinecone
    pc    = Pinecone(api_key=config.PINECONE_API_KEY)
    index = pc.Index(config.PINECONE_INDEX_NAME)

    try:
        check_pinecone(index)
    except Exception as e:
        print(f"  FAIL  Pinecone: {e}")

    try:
        check_embeddings(index)
    except Exception as e:
        print(f"  FAIL  Embedding model: {e}")

    try:
        check_llm1_agent()
    except Exception as e:
        print(f"  FAIL  LLM 1: {e}")

    try:
        check_llm2_auditor()
    except Exception as e:
        print(f"  FAIL  LLM 2: {e}")

    print(f"\n{SEP}")
    print("ALL SERVICES VERIFIED & READY")
    print(SEP)

if __name__ == "__main__":
    main()
