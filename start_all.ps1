$env:PYTHONPATH="c:\users\seraphindra\Desktop\sahulatkar;c:\users\seraphindra\Desktop\sahulatkar\packages\shared-python"
$env:DATABASE_URL="postgresql+asyncpg://sk_app:localdev123@localhost:5432/sahulatkar"
$redis_base = "redis://:localdev123@localhost:6379/"
$uvicorn = "c:\users\seraphindra\Desktop\sahulatkar\.venv\Scripts\uvicorn.exe"

$services = @(
    @{ name="gateway"; port=8000; db=0; dir="apps/gateway" },
    @{ name="product-service"; port=8001; db=1; dir="apps/product-service" },
    @{ name="credit-engine"; port=8002; db=2; dir="apps/credit-engine" },
    @{ name="payment-orchestrator"; port=8003; db=3; dir="apps/payment-orchestrator" },
    @{ name="ledger-service"; port=8004; db=4; dir="apps/ledger-service" },
    @{ name="notification-service"; port=8005; db=5; dir="apps/notification-service" }
)

foreach ($s in $services) {
    Write-Host "Starting $($s.name) on port $($s.port)..."
    $env:REDIS_URL = "$($redis_base)$($s.db)"
    $env:SERVICE_NAME = $s.name
    Start-Process $uvicorn -ArgumentList "src.main:app --port $($s.port) --host 0.0.0.0" -WorkingDirectory (Join-Path (Get-Location) $s.dir) -WindowStyle Hidden
}
