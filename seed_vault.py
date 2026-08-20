"""
seed_vault.py
=============
Reads all .txt documents from the vault/ directory, chunks them into
overlapping windows, embeds each chunk, and upserts into Pinecone.

Run once to populate the vector index:
    python seed_vault.py

Re-run after adding new vault documents to update the index.
"""
import sys
from pathlib import Path

# Ensure project root & vendor dir are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
VENDOR_DIR = PROJECT_ROOT / "vendor"
if VENDOR_DIR.exists() and str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

from app import config

# ── Naming convention parser ─────────────────────────────────────────────────
# Maps filename prefixes to a human-readable category label.
# Files that don't match any prefix fall back to "General".
_CATEGORY_MAP: dict[str, str] = {
    "employee":  "HR-Executive-Compensation",
    "patient":   "Medical-PHI",
    "ma_deal":   "Financial-MnA",
    "infra":     "Infrastructure-Secrets",
    "ip_":       "IP-Algorithm",
    "legal":     "Legal-NDA",
    "board":     "Corporate-Governance",
    "payroll":   "Finance-Payroll",
}

def _infer_category(filename: str) -> str:
    stem = filename.lower()
    for prefix, category in _CATEGORY_MAP.items():
        if stem.startswith(prefix):
            return category
    return "General"

def _make_doc_id(filename: str) -> str:
    """Convert a vault filename into a stable document ID."""
    stem = Path(filename).stem.upper().replace("_", "-")
    return f"DOC-{stem}"


# ── Text chunking ─────────────────────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = 200, overlap: int = 40) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start : start + chunk_size]))
        start += chunk_size - overlap
    return chunks


# ── Seeder ────────────────────────────────────────────────────────────────────
def seed() -> None:
    config.validate()

    print("=" * 60)
    print("AEGIS VAULT SEEDER")
    print(f"  Vault directory : {config.VAULT_DIR}")
    print(f"  Pinecone index  : {config.PINECONE_INDEX_NAME}")
    print(f"  Embedding model : {config.EMBEDDING_MODEL_NAME}")
    print("=" * 60)

    vault_files = sorted(config.VAULT_DIR.glob("*.txt"))
    if not vault_files:
        print(f"\n[WARN] No .txt files found in {config.VAULT_DIR}")
        return

    print(f"\nDiscovered {len(vault_files)} vault document(s):\n")

    model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
    pc    = Pinecone(api_key=config.PINECONE_API_KEY)
    index = pc.Index(config.PINECONE_INDEX_NAME)

    total_vectors = 0

    for vault_file in vault_files:
        doc_id   = _make_doc_id(vault_file.name)
        category = _infer_category(vault_file.name)

        raw_text = vault_file.read_text(encoding="utf-8")

        # Strip decoration lines (===, ---) and blank lines
        clean_lines = [
            line.strip() for line in raw_text.splitlines()
            if line.strip()
            and not line.strip().startswith("=")
            and not line.strip().startswith("-")
        ]
        clean_text = " ".join(clean_lines)

        chunks = chunk_text(clean_text)
        print(f"  [{doc_id}]  {len(chunks)} chunk(s)  ({category})")

        vectors = [
            {
                "id":     f"{doc_id}-chunk-{i}",
                "values": model.encode(chunk).tolist(),
                "metadata": {
                    "source":      doc_id,
                    "category":    category,
                    "text":        chunk,
                    "chunk_index": i,
                    "filename":    vault_file.name,
                },
            }
            for i, chunk in enumerate(chunks)
        ]

        # Upsert in batches of 50 (Pinecone limit)
        for batch_start in range(0, len(vectors), 50):
            index.upsert(vectors=vectors[batch_start : batch_start + 50])

        total_vectors += len(vectors)

    print(f"\nDone! {total_vectors} total vectors upserted into '{config.PINECONE_INDEX_NAME}'.")
    print("=" * 60)


if __name__ == "__main__":
    seed()