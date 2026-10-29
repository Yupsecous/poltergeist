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
if ($Only.Count -gt 0) {
    # "-File" passes "a,b" as one string, so split it here.
    $wanted = $Only | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() }
    $runs = $runs | Where-Object { $wanted -contains $_.Label }
}

foreach ($run in $runs) {
    $model = Join-Path $Models $run.File
    if (-not (Test-Path $model)) { throw "missing model file: $model" }
    # A server left over from an earlier run would answer the health check, and its model would be benchmarked under this label.
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "port $Port is already in use; stop the other llama-server first" }
    Write-Host "=== $($run.Label)"
    # Not "$server": variable names are case-insensitive, and that would overwrite the -Server parameter.
    $proc = Start-Process -FilePath $Server -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput "runtime\server-$($run.Label).out.log" -RedirectStandardError "runtime\server-$($run.Label).err.log" `
        -ArgumentList @("--model", $model, "--host", "127.0.0.1", "--port", $Port, "--ctx-size", 4096, "--threads", $Threads, "--no-webui")
    try {
        $ready = $false
        for ($i = 0; $i -lt 180 -and -not $ready; $i++) {
            Start-Sleep -Seconds 1
            if ($proc.HasExited) { throw "llama-server exited early; see runtime\server-$($run.Label).err.log" }
            try { $ready = (Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
        }
        if (-not $ready) { throw "llama-server did not become ready in 180 seconds" }
        python -m poltergeist bench --url "http://127.0.0.1:$Port" --label $run.Label
        if ($LASTEXITCODE -ne 0) { throw "bench failed for $($run.Label)" }
    }
    finally {
        if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
    }
}

# Not Tee-Object: Windows PowerShell 5.1 would save the table as UTF-16 with a byte order mark.
$table = python -m poltergeist report (Get-ChildItem results\*.json | ForEach-Object { $_.FullName })
$table | Write-Host
[System.IO.File]::WriteAllText((Join-Path $root "results\TABLE.md"), (($table -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
