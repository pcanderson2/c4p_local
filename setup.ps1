# C4P Social Monitor — Windows setup helper
# Run from the project directory: .\setup.ps1

Write-Host "=== C4P Social Monitor Setup ===" -ForegroundColor Cyan

# 1. Copy env file if not present
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[1/3] Created .env from template — edit it before continuing." -ForegroundColor Yellow
    Start-Process notepad ".env"
    Read-Host "Press Enter after saving .env to continue"
} else {
    Write-Host "[1/3] .env already exists." -ForegroundColor Green
}

# 2. Check Docker is running
try {
    docker info | Out-Null
    Write-Host "[2/3] Docker is running." -ForegroundColor Green
} catch {
    Write-Host "[2/3] ERROR: Docker Desktop is not running. Start it and re-run this script." -ForegroundColor Red
    exit 1
}

# 3. Build and start
Write-Host "[3/3] Building images and starting stack..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host ""
Write-Host "Stack is starting. The DeepSeek R1 model will download on first boot (~9 GB)." -ForegroundColor Yellow
Write-Host "Watch progress with: docker compose logs -f ollama-init" -ForegroundColor Gray
Write-Host ""
Write-Host "Postiz dashboard -> http://localhost:5000" -ForegroundColor Cyan
Write-Host "Ollama API       -> http://localhost:11434" -ForegroundColor Cyan
