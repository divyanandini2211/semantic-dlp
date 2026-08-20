# Aegis Semantic DLP

> **Semantic Data Loss Prevention** — detects when an AI agent's output carries
> sensitive information in non-standard form: paraphrased, summarised, or
> factually reconstructed from a protected document vault.

Standard DLP tools block known patterns (email, SSN, credit card numbers).
Aegis catches semantic exfiltration that bypasses all pattern-matching.

---

## How It Works

Every agent output is run through a 3-stage pipeline:

```
Output Text
    │
    ▼  Stage 1 — Regex PII Scanner
    │  Instant block on email, SSN, AWS key patterns
    │
    ▼  Stage 2 — Dense Vector Similarity (Pinecone)
    │  Cosine distance vs. protected vault embeddings
    │  score >= 0.78 → instant BLOCK with lineage tag
    │
    ▼  Stage 3 — LLM Factual Overlap Auditor (Groq)
       Judges whether specific vault facts appear,
       even when heavily paraphrased or obfuscated
       → ALLOW or BLOCK
```

---

## Quick Start

### 1. Clone & install

```bash
git clone <repo-url>
cd semantic-dlp
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in GROQ_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME
```

### 3. Seed the vault

```bash
python seed_vault.py
```

Reads every `.txt` file in `vault/`, chunks and embeds it, and upserts
into your Pinecone index. Re-run whenever you add new protected documents.

### 4. Run the API server

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. Verify everything is healthy

```bash
python scripts/verify_vault.py
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/vault/status
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/inspect` | Inspect an agent output for vault leakage |
| `GET` | `/api/v1/vault/status` | Pinecone index stats (vector count etc.) |
| `GET` | `/api/v1/audit/logs` | Paginated audit log (recent decisions) |
| `DELETE` | `/api/v1/audit/logs` | Clear audit log (dev/admin) |
| `GET` | `/health` | Liveness probe |

**Interactive docs:** http://localhost:8000/docs

### Inspect request

```json
POST /api/v1/inspect
{
  "agent_id": "my-agent",
  "output_text": "The CTO earns EUR 380,000 per year with 15,000 RSUs vesting annually."
}
```

### Response (BLOCK)

```json
{
  "decision": "BLOCK",
  "details": {
    "similarity_score": 0.5702,
    "factual_overlap": true,
    "reason": "Semantic factual exfiltration detected: output reconstructs HR compensation facts",
    "lineage_tag": "DOC-EMPLOYEE-RECORD-CTO",
    "extracted_facts": ["EUR 380,000 base salary", "15,000 RSUs annual grant"],
    "trace": [
      "Stage 1 (Regex): PASSED - No PII matched",
      "Stage 2 (Vector Math): PASSED (Score: 0.57 < 0.78)",
      "Stage 3 (LLM Auditor): BLOCKED - Deep factual leak detected"
    ]
  }
}
```

---

## Project Structure

```
semantic-dlp/
├── app/
│   ├── config.py        # Central config (env vars + path constants)
│   ├── core_logic.py    # 3-stage detection pipeline
│   ├── main.py          # FastAPI app + all API endpoints
│   └── __init__.py
├── vault/               # Protected reference documents (.txt)
├── tests/
│   ├── corpus.json      # Frozen 20-case test suite
│   ├── generate_corpus.py  # Regenerate corpus from LLM prompts
│   └── test_bench.py    # Benchmark runner
├── scripts/
│   └── verify_vault.py  # Dev utility: check API keys + vault
├── seed_vault.py        # Embed vault docs → Pinecone
├── .env.example         # Environment template
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Running the Benchmark

With the API server running:

```bash
python tests/test_bench.py
```

**Target criteria:**
- Paraphrased leaks detected: ≥ 4/5 (80%)
- False positive rate on normal outputs: < 20%
- Zero system API errors

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | — | **Required.** Groq API key |
| `PINECONE_API_KEY` | — | **Required.** Pinecone API key |
| `PINECONE_INDEX_NAME` | `dlp` | Pinecone index name |
| `EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | Sentence-transformer model |
| `GROQ_MODEL` | `qwen/qwen3.6-27b` | Groq LLM for factual auditing |
| `SIMILARITY_HIGH_THRESHOLD` | `0.78` | Instant-block threshold (Stage 2) |
| `SIMILARITY_CHECK_FLOOR` | `0.35` | LLM-auditor trigger threshold (Stage 3) |
| `CORS_ORIGINS` | `*` | Allowed frontend origins (comma-separated) |

---

## Adding New Vault Documents

1. Drop a `.txt` file into `vault/`
2. Name it descriptively (e.g. `patient_record_JD2027.txt`)
3. Re-run `python seed_vault.py`

The seeder auto-discovers all `.txt` files and derives a document ID
and category label from the filename.

---

## Docker

```bash
docker build -t aegis-dlp .
docker run -p 8080:8080 --env-file .env aegis-dlp
```