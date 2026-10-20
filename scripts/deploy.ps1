<#
.SYNOPSIS
  Build images and deploy AI Cost Governor to Docker Desktop Kubernetes.

.EXAMPLE
  .\scripts\deploy.ps1              # build + deploy
  .\scripts\deploy.ps1 -SkipBuild   # redeploy with existing images

  Then open http://localhost:8080 and sign in as admin@test.com / demo123.
#>
param(
    [string]$Context = 'docker-desktop',
    [switch]$SkipBuild,
    [switch]$SkipMetricsServer
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$ns = 'acg'
$images = 'acg-backend:latest', 'acg-mock-llm:latest', 'acg-frontend:latest'

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# --- 0. Preconditions -------------------------------------------------------
docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker is not running. Start Docker Desktop first.' }

# Every kubectl call names the cluster explicitly instead of switching the
# global current-context, so other projects' terminals keep pointing at
# whatever cluster they were using.
kubectl config get-contexts $Context -o name 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "No kubectl context '$Context'. Enable Kubernetes in Docker Desktop (Settings > Kubernetes)."
}
function kc { kubectl --context $Context @args }
Step "Deploying to kubectl context '$Context' (your current context is left unchanged)"

# --- 1. Images ---------------------------------------------------------------
if (-not $SkipBuild) {
    Step 'Building images'
    docker build -t acg-backend:latest   "$root\backend"
    if ($LASTEXITCODE -ne 0) { throw 'backend image build failed' }
    docker build -t acg-mock-llm:latest  "$root\services\mock-llm"
    if ($LASTEXITCODE -ne 0) { throw 'mock-llm image build failed' }
    docker build -t acg-frontend:latest  "$root\frontend"
    if ($LASTEXITCODE -ne 0) { throw 'frontend image build failed' }
}

# Docker Desktop's built-in (kubeadm) cluster sees local images directly.
# A kind cluster (context "kind-<name>", including Docker Desktop's kind mode)
# has its own image store, so images must be loaded into its nodes.
if ($Context -like 'kind-*') {
    $kindName = $Context.Substring(5)
    Step "Loading images into kind cluster '$kindName'"
    foreach ($img in $images) { kind load docker-image $img --name $kindName }
}

# --- 2. Secret from backend/.env -------------------------------------------
Step 'Creating Secret acg-secrets from backend/.env'
$envVars = @{}
Get-Content "$root\backend\.env" | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $envVars[$matches[1]] = $matches[2].Trim() }
}
foreach ($k in 'JWT_SECRET', 'ENCRYPTION_KEY', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD') {
    if (-not $envVars[$k]) { throw "backend/.env is missing $k" }
}
$dbUrl = "postgresql://$($envVars.POSTGRES_USER):$($envVars.POSTGRES_PASSWORD)@postgres:5432/$($envVars.POSTGRES_DB)"

kc apply -f "$root\deploy\k8s\namespace.yaml" | Out-Null
kc -n $ns create secret generic acg-secrets `
    --from-literal=JWT_SECRET="$($envVars.JWT_SECRET)" `
    --from-literal=ENCRYPTION_KEY="$($envVars.ENCRYPTION_KEY)" `
    --from-literal=POSTGRES_DB="$($envVars.POSTGRES_DB)" `
    --from-literal=POSTGRES_USER="$($envVars.POSTGRES_USER)" `
    --from-literal=POSTGRES_PASSWORD="$($envVars.POSTGRES_PASSWORD)" `
    --from-literal=DATABASE_URL="$dbUrl" `
    --dry-run=client -o yaml | kubectl --context $Context apply -f -

# --- 3. metrics-server (needed by the HPA; not bundled with Docker Desktop) --
if (-not $SkipMetricsServer) {
    $ms = kc -n kube-system get deployment metrics-server --ignore-not-found -o name
    if (-not $ms) {
        Step 'Installing metrics-server'
        kc apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.7.2/components.yaml
        # Docker Desktop's kubelet uses a self-signed cert.
        kc -n kube-system patch deployment metrics-server --type=json `
            -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
    }
}

# --- 4. Workloads ------------------------------------------------------------
Step 'Applying manifests (kubectl apply -k deploy/k8s)'
kc apply -k "$root\deploy\k8s"

Step 'Waiting for Postgres and Redis'
kc -n $ns rollout status statefulset/postgres --timeout=180s
kc -n $ns rollout status deployment/redis --timeout=120s

Step 'Seeding demo data (Job)'
kc -n $ns delete job seed-demo --ignore-not-found | Out-Null
kc apply -f "$root\deploy\k8s\seed-job.yaml"
kc -n $ns wait --for=condition=complete job/seed-demo --timeout=300s
kc -n $ns logs job/seed-demo --tail=12

# Restart app pods so they pick up a rebuilt :latest image.
if (-not $SkipBuild) {
    kc -n $ns rollout restart deployment/gateway deployment/usage-worker deployment/alert-worker deployment/mock-llm deployment/frontend | Out-Null
}

Step 'Waiting for application pods'
foreach ($d in 'mock-llm', 'gateway', 'usage-worker', 'alert-worker', 'frontend') {
    kc -n $ns rollout status deployment/$d --timeout=180s
}

kc -n $ns get pods -o wide
Write-Host "`nDashboard: http://localhost:8080   (admin@test.com / demo123)" -ForegroundColor Green
