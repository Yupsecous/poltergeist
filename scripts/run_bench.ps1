# Run the ghost cases against each local model in turn, then print the results table.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run_bench.ps1 -Server C:\llama\llama-server.exe -Models C:\models
#
# llama-server is started on 127.0.0.1 only and stopped again after each model.
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Models,
    [int]$Port = 8081,
    [int]$Threads = 6,
    [string[]]$Only = @()
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force -Path "runtime", "results" | Out-Null

$runs = @(
    @{ Label = "gemma-3-1b"; File = "gemma-3-1b-it-Q4_K_M.gguf" },
    @{ Label = "qwen2.5-3b"; File = "qwen2.5-3b-instruct-q4_k_m.gguf" },
    @{ Label = "gemma-3-4b"; File = "gemma-3-4b-it-Q4_K_M.gguf" }
)
if ($Only.Count -gt 0) { $runs = $runs | Where-Object { $Only -contains $_.Label } }

foreach ($run in $runs) {
    $model = Join-Path $Models $run.File
    if (-not (Test-Path $model)) { throw "missing model file: $model" }
    Write-Host "=== $($run.Label)"
    $server = Start-Process -FilePath $Server -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput "runtime\server-$($run.Label).out.log" -RedirectStandardError "runtime\server-$($run.Label).err.log" `
        -ArgumentList @("--model", $model, "--host", "127.0.0.1", "--port", $Port, "--ctx-size", 4096, "--threads", $Threads, "--no-webui")
    try {
        $ready = $false
        for ($i = 0; $i -lt 180 -and -not $ready; $i++) {
            Start-Sleep -Seconds 1
            if ($server.HasExited) { throw "llama-server exited early; see runtime\server-$($run.Label).err.log" }
            try { $ready = (Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
        }
        if (-not $ready) { throw "llama-server did not become ready in 180 seconds" }
        python -m poltergeist bench --url "http://127.0.0.1:$Port" --label $run.Label
        if ($LASTEXITCODE -ne 0) { throw "bench failed for $($run.Label)" }
    }
    finally {
        if (-not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    }
}

python -m poltergeist report (Get-ChildItem results\*.json | ForEach-Object { $_.FullName }) | Tee-Object -FilePath results\TABLE.md
