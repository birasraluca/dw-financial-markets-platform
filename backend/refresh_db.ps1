Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "DW PROJECT - FULL DATABASE REFRESH" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 1) Clear DB
Write-Host "`n[1/4] Clearing database..." -ForegroundColor Yellow
python refresh_db.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "Database reset failed." -ForegroundColor Red
    exit 1
}

# 2) Check backend
Write-Host "`n[2/4] Checking backend availability..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:5000/" -Method GET -TimeoutSec 10
    Write-Host "Backend is running." -ForegroundColor Green
}
catch {
    Write-Host "Backend is not reachable at http://localhost:5000" -ForegroundColor Red
    Write-Host "Start your Flask backend first, then run this script again." -ForegroundColor Red
    exit 1
}

# Helper: run Binance ingestion
function Run-BinanceIngestion {
    param(
        [string]$Symbol,
        [string]$Name,
        [string]$Interval = "1d",
        [string]$From = "2024-01-01",
        [string]$To = "2024-12-31"
    )

    $body = @{
        symbol   = $Symbol
        name     = $Name
        interval = $Interval
        from     = $From
        to       = $To
    } | ConvertTo-Json -Compress

    Write-Host "  -> Binance: $Symbol ($Name)" -ForegroundColor DarkCyan

    try {
        $response = Invoke-RestMethod `
            -Uri "http://localhost:5000/ingestions/run/binance" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -TimeoutSec 120

        $inserted = if ($null -ne $response.rows_inserted) { $response.rows_inserted } else { 0 }
        $skipped  = if ($null -ne $response.rows_skipped) { $response.rows_skipped } else { 0 }

        Write-Host "     Success | inserted=$inserted skipped=$skipped" -ForegroundColor Green
    }
    catch {
        Write-Host "     Failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# Helper: run Frankfurter ingestion
function Run-FrankfurterIngestion {
    param(
        [string]$Base,
        [string]$Quote,
        [string]$From = "2024-01-01",
        [string]$To = "2024-12-31"
    )

    $body = @{
        base  = $Base
        quote = $Quote
        from  = $From
        to    = $To
    } | ConvertTo-Json -Compress

    Write-Host "  -> Frankfurter: $Base/$Quote" -ForegroundColor DarkMagenta

    try {
        $response = Invoke-RestMethod `
            -Uri "http://localhost:5000/ingestions/run/frankfurter" `
            -Method POST `
            -ContentType "application/json" `
            -Body $body `
            -TimeoutSec 120

        $inserted = if ($null -ne $response.rows_inserted) { $response.rows_inserted } else { 0 }
        $skipped  = if ($null -ne $response.rows_skipped) { $response.rows_skipped } else { 0 }

        Write-Host "     Success | inserted=$inserted skipped=$skipped" -ForegroundColor Green
    }
    catch {
        Write-Host "     Failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# 3) Reimport data
Write-Host "`n[3/4] Running ingestions..." -ForegroundColor Yellow

# Crypto set
$binanceAssets = @(
    @{ symbol = "BTCUSDT"; name = "Bitcoin / Tether" },
    @{ symbol = "ETHUSDT"; name = "Ethereum / Tether" },
    @{ symbol = "BNBUSDT"; name = "BNB / Tether" },
    @{ symbol = "SOLUSDT"; name = "Solana / Tether" },
    @{ symbol = "XRPUSDT"; name = "XRP / Tether" },
    @{ symbol = "ADAUSDT"; name = "Cardano / Tether" }
)

foreach ($asset in $binanceAssets) {
    Run-BinanceIngestion `
        -Symbol $asset.symbol `
        -Name $asset.name `
        -Interval "1d" `
        -From "2024-01-01" `
        -To "2024-12-31"
}

# FX set
$fxPairs = @(
    @{ base = "EUR"; quote = "USD" },
    @{ base = "GBP"; quote = "USD" },
    @{ base = "EUR"; quote = "GBP" },
    @{ base = "USD"; quote = "JPY" },
    @{ base = "EUR"; quote = "RON" },
    @{ base = "USD"; quote = "RON" }
)

foreach ($pair in $fxPairs) {
    Run-FrankfurterIngestion `
        -Base $pair.base `
        -Quote $pair.quote `
        -From "2024-01-01" `
        -To "2024-12-31"
}

# 4) Quick verification
Write-Host "`n[4/4] Verifying refresh..." -ForegroundColor Yellow

try {
    $assets = Invoke-RestMethod -Uri "http://localhost:5000/assets" -Method GET -TimeoutSec 30
    $sources = Invoke-RestMethod -Uri "http://localhost:5000/sources" -Method GET -TimeoutSec 30
    $combinations = Invoke-RestMethod -Uri "http://localhost:5000/lookup/valid-combinations" -Method GET -TimeoutSec 30
    $ingestions = Invoke-RestMethod -Uri "http://localhost:5000/ingestions/recent" -Method GET -TimeoutSec 30

    $assetCount = if ($assets) { $assets.Count } else { 0 }
    $sourceCount = if ($sources) { $sources.Count } else { 0 }
    $comboCount = if ($combinations) { $combinations.Count } else { 0 }
    $ingestionCount = if ($ingestions) { $ingestions.Count } else { 0 }

    Write-Host "`nRefresh complete." -ForegroundColor Green
    Write-Host "Assets: $assetCount" -ForegroundColor Cyan
    Write-Host "Sources: $sourceCount" -ForegroundColor Cyan
    Write-Host "Valid combinations: $comboCount" -ForegroundColor Cyan
    Write-Host "Recent ingestions: $ingestionCount" -ForegroundColor Cyan
}
catch {
    Write-Host "Verification step failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nDone." -ForegroundColor Green