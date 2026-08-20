"""
seed_vault.py — Reads full synthetic documents from vault/, chunks them,
embeds each chunk, and upserts into Pinecone.
"""
import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
model = SentenceTransformer("all-MiniLM-L6-v2")

VAULT_FILES = [
    {"file": "vault/employee_record_CTO.txt",    "doc_id": "DOC-HR-SALARY-EXEC-2026",   "category": "HR-Executive-Compensation"},
    {"file": "vault/patient_record_MV8812.txt",  "doc_id": "DOC-MED-PATIENT-8812",      "category": "Medical-PHI"},
    {"file": "vault/ma_deal_falcon.txt",          "doc_id": "DOC-FIN-2026-Q3-MERGER",    "category": "Financial-MnA"},
    {"file": "vault/infra_prod_keys.txt",         "doc_id": "DOC-INFRA-PROD-KEYS",       "category": "Infrastructure-Secrets"},
    {"file": "vault/ip_algorithm_v4.txt",         "doc_id": "DOC-RD-ALGO-V4",            "category": "IP-Algorithm"},
    {"file": "vault/legal_nda_2026.txt",          "doc_id": "DOC-LEGAL-NDA-2026",        "category": "Legal-NDA"},
    {"file": "vault/board_minutes_Q2_2026.txt",   "doc_id": "DOC-BOARD-MINUTES-Q2-2026", "category": "Corporate-Governance"},
    {"file": "vault/payroll_report_Q2_2026.txt",  "doc_id": "DOC-FIN-PAYROLL-Q2-2026",   "category": "Finance-Payroll"},
]

def chunk_text(text, chunk_size=200, overlap=40):
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start:start + chunk_size]))
        start += chunk_size - overlap
    return chunks

def seed():
    print("Seeding Pinecone with full document vault (8 documents)...\n")
    total_vectors = 0

    for entry in VAULT_FILES:
        path = entry["file"]
        if not os.path.exists(path):
            print(f"  [SKIP] File not found: {path}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # Strip decoration lines, keep meaningful content
        lines = [l.strip() for l in raw_text.splitlines()
                 if l.strip() and not l.strip().startswith("=") and not l.strip().startswith("-")]
        clean_text = " ".join(lines)

        chunks = chunk_text(clean_text)
        print(f"  [{entry['doc_id']}] {len(chunks)} chunks")

        vectors = []
        for i, chunk in enumerate(chunks):
            embedding = model.encode(chunk).tolist()
            vectors.append({
                "id": f"{entry['doc_id']}-chunk-{i}",
                "values": embedding,
                "metadata": {
                    "source": entry["doc_id"],
                    "category": entry["category"],
                    "text": chunk[:500],
                    "chunk_index": i
                }
            })

        for batch_start in range(0, len(vectors), 50):
            index.upsert(vectors=vectors[batch_start:batch_start + 50])
        total_vectors += len(vectors)

    print(f"\nDone! {total_vectors} total vectors upserted into Pinecone.")

if __name__ == "__main__":
    seed()