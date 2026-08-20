# ==============================================================================
# Aegis Semantic DLP Shield — AWS App Runner / ECR Deployment (PowerShell)
# ==============================================================================

param (
    [string]$AwsRegion = "us-east-1",
    [string]$ImageTag = "latest"
)

$ErrorActionPreference = "Stop"
$ImageRepoName = "aegis-semantic-dlp"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "DEPLOYING AEGIS SEMANTIC DLP TO AWS" -ForegroundColor Cyan
Write-Host "Region: $AwsRegion"
Write-Host "========================================================================"

# 1. Fetch AWS Account ID
$AwsAccountId = aws sts get-caller-identity --query Account --output text
$EcrUri = "$AwsAccountId.dkr.ecr.$AwsRegion.amazonaws.com/$ImageRepoName"

# 2. Check / Create ECR repository
Write-Host "[1/4] Checking AWS ECR repository..." -ForegroundColor Yellow
try {
    aws ecr describe-repositories --repository-names $ImageRepoName --region $AwsRegion | Out-Null
} catch {
    Write-Host "Creating ECR repository '$ImageRepoName'..."
    aws ecr create-repository --repository-name $ImageRepoName --region $AwsRegion | Out-Null
}

# 3. Authenticate Docker with ECR
Write-Host "[2/4] Authenticating with AWS ECR..." -ForegroundColor Yellow
$loginPassword = aws ecr get-login-password --region $AwsRegion
$loginPassword | docker login --username AWS --password-stdin "$AwsAccountId.dkr.ecr.$AwsRegion.amazonaws.com"

# 4. Build Docker container
Write-Host "[3/4] Building production Docker image..." -ForegroundColor Yellow
docker build -t "$ImageRepoName`:$ImageTag" .
docker tag "$ImageRepoName`:$ImageTag" "$EcrUri`:$ImageTag"

# 5. Push to ECR
Write-Host "[4/4] Pushing image to AWS ECR..." -ForegroundColor Yellow
docker push "$EcrUri`:$ImageTag"

Write-Host "========================================================================" -ForegroundColor Green
Write-Host "IMAGE PUSHED TO AWS ECR!" -ForegroundColor Green
Write-Host "Image URI: $EcrUri`:$ImageTag" -ForegroundColor White
Write-Host ""
Write-Host "Next steps on AWS Console:"
Write-Host "1. Open AWS App Runner -> Create Service"
Write-Host "2. Select 'Container Registry' -> Amazon ECR"
Write-Host "3. Image: $EcrUri`:$ImageTag"
Write-Host "4. Port: 8080"
Write-Host "5. Set Environment Variables: GROQ_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME"
Write-Host "6. Click Deploy to get your live https://...awsapprunner.com URL"
Write-Host "========================================================================" -ForegroundColor Green
