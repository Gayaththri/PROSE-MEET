# Upload PROSE-MEET to Hugging Face Space using HF_TOKEN (Write access).
# Usage:
#   $env:HF_TOKEN="hf_your_write_token"
#   .\scripts\push-hf-space.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

if (-not $env:HF_TOKEN) {
    Write-Host ""
    Write-Host "HF_TOKEN is not set." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Open https://huggingface.co/settings/tokens"
    Write-Host "2. Create a token with Write access"
    Write-Host "3. Run:"
    Write-Host '   $env:HF_TOKEN="hf_..."' -ForegroundColor Cyan
    Write-Host "   .\scripts\push-hf-space.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

Set-Location $Root
python scripts/push_hf_space.py
exit $LASTEXITCODE
