# Aegis Semantic DLP Shield (PS-5.3)

> **Enterprise Semantic Data Loss Prevention & Exfiltration Guardrail**  
> Intercepts AI agent outputs and detects confidential data leaks derived from protected document vaults — even when heavily paraphrased, summarized, disguised, or factually reconstructed without direct keyword quotes.

---

## 🛡️ Key Features & Problem Statement Deliverables

* **Reference Data Vault:** Pinecone Cloud Vector Store (32 dense 384-dim embeddings across Financial M&A, Executive Comp, Patient PHI, Infrastructure Keys, and R&D specs).
* **3-Tier Inspection Pipeline:**
  1. **Stage 1 (Regex PII Scanner):** Fast deterministic filtering for structured credentials.
  2. **Stage 2 (Dense Vector Similarity):** Semantic distance against Pinecone Cloud.
  3. **Stage 3 (Dual-LLM Factual Auditor):** Independent security judge (`openai/gpt-oss-120b`) reasoning about specific fact overlap.
* **Data Lineage Tagging (Bonus Criteria):** Source lineage tags (`DOC-MA-DEAL-FALCON`, `DOC-MED-PATIENT-8812`) stamped in chat cards, metadata, and SQLite audit logs.
* **Production Web UI:** Pure minimalist black-and-white interface with live chat simulation, 20-sample automated suite runner, interactive pipeline stage inspector dialog, and PS-5.3 compliance summary modal.

---

## 🚀 Quick Start (Local)

### 1. Clone & Setup Python Environment
```bash
git clone <repo-url>
cd semantic-dlp
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create `.env` based on `.env.example`:
```ini
GROQ_API_KEY=gsk_...
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX_NAME=dlp
PINECONE_ENVIRONMENT=us-east-1
AGENT_LLM_MODEL=openai/gpt-oss-20b
AUDITOR_LLM_MODEL=openai/gpt-oss-120b
PORT=8080
```

### 3. Seed the Pinecone Cloud Vault (If not already seeded)
```bash
python seed_vault.py
```

### 4. Start the Application
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
Open **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)** in your browser.

---

## 🐳 Docker Deployment

### Run with Docker Compose
```bash
docker-compose up --build -d
```
Verify container status:
```bash
curl http://localhost:8080/health
```

---

## ☁️ AWS Cloud Deployment Guide

### Option A: AWS App Runner (Recommended — Fully Managed Serverless)
AWS App Runner provides automated scaling, SSL/HTTPS certificates, and health check monitoring with zero EC2 maintenance.

1. **Push Image to AWS ECR:**
   * On Linux/macOS:
     ```bash
     chmod +x scripts/aws_deploy.sh
     ./scripts/aws_deploy.sh
     ```
   * On Windows PowerShell:
     ```powershell
     .\scripts\aws_deploy.ps1
     ```
2. **Create App Runner Service:**
   * Go to **AWS Console** $\to$ **App Runner** $\to$ **Create Service**.
   * Source: **Container Registry** $\to$ **Amazon ECR**.
   * Select your repository image URI (`<account-id>.dkr.ecr.us-east-1.amazonaws.com/aegis-semantic-dlp:latest`).
   * Port: `8080`.
   * Add Environment Variables:
     * `GROQ_API_KEY`
     * `PINECONE_API_KEY`
     * `PINECONE_INDEX_NAME` (`dlp`)
     * `PINECONE_ENVIRONMENT` (`us-east-1`)
   * Click **Create & Deploy**.
   * App Runner will automatically provide your live HTTPS URL: `https://<random-id>.us-east-1.awsapprunner.com/`.

---

### Option B: AWS ECS Fargate
1. Define an ECS Task Definition with container port `8080`.
2. Set CPU to `1 vCPU` and Memory to `2 GB`.
3. Link AWS Application Load Balancer (ALB) pointing to target group on port `8080` with health check path `/health`.

---

## 🧪 20-Sample Benchmark Test Suite

To run the full 20-sample validation suite against the active service:
```bash
python tests/test_bench.py
```

### Success Criteria Summary:
* **Paraphrased Leak Recall:** **100.0% (5/5)** `[Target: ≥ 80%]`
* **False Positive Rate on Normal:** **0.0% (0/10)** `[Target: < 20%]`
* **Fact Obfuscation Resilience:** **100% PASS**
* **Data Lineage Tagging:** **Active & Verified**

---

## 📡 API Reference

* `POST /api/v1/agent/chat` — Live conversational agent with inline DLP guardrail.
* `POST /api/v1/inspect` — Inspect raw agent output payloads.
* `GET /api/v1/attacks/presets` — List curated 20-sample attack & normal presets.
* `GET /api/v1/vault/status` — Live Pinecone Cloud vector metrics.
* `GET /api/v1/vault/documents` — List indexed cloud vault records.
* `GET /api/v1/audit/logs` — Query SQLite inspection history (IST timestamps).
* `GET /health` — Production liveness & health check probe.
* Interactive Swagger Docs: `http://localhost:8080/docs`