import os
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "dlp-vault")

if not PINECONE_API_KEY:
    raise ValueError("Missing PINECONE_API_KEY in environment variables.")

model = SentenceTransformer("all-MiniLM-L6-v2")
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

# Reference Protected Vault Documents
VAULT_DOCUMENTS = [
    {
        "id": "vault-fin-001",
        "category": "Financial",
        "source": "DOC-FIN-2026-Q3-MERGER",
        "text": "Project Falcon involves the acquisition of CloudScale Inc for 45 million USD, scheduled for completion in November 2026 under lead partner David Sterling."
    },
    {
        "id": "vault-hr-002",
        "category": "Employee HR",
        "source": "DOC-HR-SALARY-EXEC-2026",
        "text": "Chief Technology Officer Elena Rostova receives a base compensation of 380,000 EUR with an equity grant of 15,000 restricted stock units vesting annually."
    },
    {
        "id": "vault-med-003",
        "category": "Medical Record",
        "source": "DOC-MED-PATIENT-8812",
        "text": "Patient Marcus Vance (DOB 1984-05-12) diagnosed with refractory cardiac arrhythmia, prescribed Sotalol 80mg twice daily with restricted physical exertion."
    },
    {
        "id": "vault-infra-004",
        "category": "Infrastructure Secrets",
        "source": "DOC-INFRA-PROD-KEYS",
        "text": "Production Kubernetes bastion host IP is 10.240.18.99 using rotating SSH key fingerprint SHA256:7uK89eEwq841 with root admin access restricted to VPN subnet."
    },
    {
        "id": "vault-rd-005",
        "category": "Intellectual Property",
        "source": "DOC-RD-ALGO-V4",
        "text": "The proprietary compression algorithm uses a modified Burrows-Wheeler transform paired with dynamic entropy encoding achieving 42 percent higher throughput."
    }
]

def seed():
    print(f"Connecting to Pinecone index '{INDEX_NAME}'...")
    vectors = []
    for doc in VAULT_DOCUMENTS:
        vector = model.encode(doc["text"]).tolist()
        vectors.append({
            "id": doc["id"],
            "values": vector,
            "metadata": {
                "text": doc["text"],
                "source": doc["source"],
                "category": doc["category"]
            }
        })
    
    index.upsert(vectors=vectors)
    print(f"✅ Successfully seeded {len(vectors)} protected documents into the Reference Data Vault.")

if __name__ == "__main__":
    seed()