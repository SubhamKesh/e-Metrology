# Run this from backend\ in PowerShell to verify all 6 fixes are in place.

Write-Host "=== 1. seed_data.py present ===" -ForegroundColor Cyan
if (Test-Path "seed\seed_data.py") { Write-Host "  OK" -ForegroundColor Green } else { Write-Host "  MISSING" -ForegroundColor Red }

Write-Host "=== 2. certificates.py has access control ===" -ForegroundColor Cyan
if (Select-String -Path "app\routers\certificates.py" -Pattern "_can_access" -Quiet) {
    Write-Host "  OK" -ForegroundColor Green
} else {
    Write-Host "  MISSING - old version still in place" -ForegroundColor Red
}

Write-Host "=== 3. dashboard_router.py deleted ===" -ForegroundColor Cyan
if (Test-Path "app\routers\dashboard_router.py") {
    Write-Host "  STILL EXISTS - delete it" -ForegroundColor Red
} else {
    Write-Host "  OK (deleted)" -ForegroundColor Green
}

Write-Host "=== 4. stale models deleted ===" -ForegroundColor Cyan
$stale = @("app\models\certificate.py", "app\models\alert.py")
$anyLeft = $false
foreach ($f in $stale) {
    if (Test-Path $f) { Write-Host "  STILL EXISTS: $f" -ForegroundColor Red; $anyLeft = $true }
}
if (-not $anyLeft) { Write-Host "  OK (both deleted)" -ForegroundColor Green }

Write-Host "=== 5. CRLF normalized ===" -ForegroundColor Cyan
$checkFiles = @("app\services\qr_generator.py", "app\utils\upload_to_cloudinary.py", "app\routers\uploads.py")
$anyCR = $false
foreach ($f in $checkFiles) {
    if (Test-Path $f) {
        $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $f))
        if ($bytes -contains 13) { Write-Host "  STILL CRLF: $f" -ForegroundColor Red; $anyCR = $true }
    }
}
if (-not $anyCR) { Write-Host "  OK (all LF)" -ForegroundColor Green }

Write-Host "=== 6. claim_application is atomic ===" -ForegroundColor Cyan
if (Select-String -Path "app\routers\applications.py" -Pattern "find_one_and_update" -Quiet) {
    Write-Host "  OK" -ForegroundColor Green
} else {
    Write-Host "  MISSING - old check-then-update still in place" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Sanity: does the app still import cleanly? ===" -ForegroundColor Cyan
python -c "from app.main import app; print('APP IMPORT OK -', len(app.routes), 'routes')"
