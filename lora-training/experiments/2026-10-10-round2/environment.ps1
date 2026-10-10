Set-Location -LiteralPath $PSScriptRoot
$env:HF_HOME = Join-Path $PSScriptRoot 'cache\huggingface'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:CUDA_CACHE_PATH = Join-Path $PSScriptRoot 'cache\cuda'
$env:UNSLOTH_COMPILE_LOCATION = Join-Path $PSScriptRoot 'cache\unsloth'
$env:TORCH_HOME = Join-Path $PSScriptRoot 'cache\torch'
$env:TORCH_EXTENSIONS_DIR = Join-Path $PSScriptRoot 'cache\torch-extensions'
$env:TORCHINDUCTOR_CACHE_DIR = Join-Path $PSScriptRoot 'cache\inductor'
$env:TRITON_CACHE_DIR = Join-Path $PSScriptRoot 'cache\triton'
$env:TEMP = Join-Path $PSScriptRoot 'cache\temp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot 'cache\pip'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot 'cache\uv'
$env:XDG_CACHE_HOME = Join-Path $PSScriptRoot 'cache'
$env:PYTHONPYCACHEPREFIX = Join-Path $PSScriptRoot 'cache\pycache'
$env:OLLAMA_MODELS = Join-Path $PSScriptRoot 'models\ollama'
$env:HF_HUB_DISABLE_XET = '1'
$env:PYTHONIOENCODING = 'utf-8'
foreach ($taskCachePath in @($env:HF_HOME,$env:HF_HUB_CACHE,$env:CUDA_CACHE_PATH,$env:UNSLOTH_COMPILE_LOCATION,$env:TORCH_HOME,$env:TORCH_EXTENSIONS_DIR,$env:TORCHINDUCTOR_CACHE_DIR,$env:TRITON_CACHE_DIR,$env:TEMP,$env:PIP_CACHE_DIR,$env:UV_CACHE_DIR,$env:PYTHONPYCACHEPREFIX,$env:OLLAMA_MODELS)) {
    if (-not (Test-Path -LiteralPath $taskCachePath)) { New-Item -ItemType Directory -Path $taskCachePath | Out-Null }
}
