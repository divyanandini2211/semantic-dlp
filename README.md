# Aegis: Semantic Data Exfiltration Detector (PS-5.3)

Production-ready semantic Data Loss Prevention (DLP) guardrail for autonomous AI agents. Built for Aivar Innovations Agentic AI Governance Assessment.

## Architecture
- **Reference Vault:** Pinecone vector index (`dlp-vault`, 384 dimensions, cosine distance)
- **Local Embedding Scorer:** Sentence-Transformers `all-MiniLM-L6-v2` (zero API cost)
- **Factual Overlap Reasoning:** Groq API (`llama-3.3-70b-versatile`) for deep semantic inference
- **Lineage Tagging:** Automatically associates flagged outputs with the specific source vault document
- **Governance Audit Trail:** In-memory structured logging accessible via REST API and Web Console

## Quickstart

1. Install dependencies:
   ```bash
   pip install -r requirements.txt