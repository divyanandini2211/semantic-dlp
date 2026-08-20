#!/usr/bin/env bash
# ==============================================================================
# Aegis Semantic DLP Shield — AWS App Runner / ECR Deployment Script
# ==============================================================================

set -euo pipefail

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
IMAGE_REPO_NAME="aegis-semantic-dlp"
IMAGE_TAG="${1:-latest}"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_REPO_NAME}"

echo "========================================================================"
echo "DEPLOYING AEGIS SEMANTIC DLP TO AWS"
echo "Target ECR URI: ${ECR_URI}:${IMAGE_TAG}"
echo "AWS Region:     ${AWS_REGION}"
echo "========================================================================"

# 1. Ensure ECR repository exists
echo "[1/4] Checking AWS ECR repository..."
aws ecr describe-repositories --repository-names "${IMAGE_REPO_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "${IMAGE_REPO_NAME}" --region "${AWS_REGION}"

# 2. Authenticate Docker with ECR
echo "[2/4] Authenticating with AWS ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# 3. Build Docker image with pre-cached model weights
echo "[3/4] Building production Docker container..."
docker build -t "${IMAGE_REPO_NAME}:${IMAGE_TAG}" .
docker tag "${IMAGE_REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"

# 4. Push to AWS ECR
echo "[4/4] Pushing image to AWS ECR..."
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "========================================================================"
echo "IMAGE SUCCESSFULLY PUSHED TO AWS ECR!"
echo "Image URI: ${ECR_URI}:${IMAGE_TAG}"
echo ""
echo "Next Steps for AWS App Runner:"
echo "1. Go to AWS App Runner Console -> Create Service"
echo "2. Source: Container Registry -> Amazon ECR"
echo "3. Container Image URI: ${ECR_URI}:${IMAGE_TAG}"
echo "4. Port: 8080"
echo "5. Add Environment Variables from .env:"
echo "   - GROQ_API_KEY"
echo "   - PINECONE_API_KEY"
echo "   - PINECONE_INDEX_NAME (dlp)"
echo "   - PINECONE_ENVIRONMENT (us-east-1)"
echo "6. Deploy -> Public HTTPS URL will be generated automatically!"
echo "========================================================================"
