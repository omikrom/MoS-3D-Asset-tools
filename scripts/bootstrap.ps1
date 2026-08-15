$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env; edit the Blender/model paths before enabling providers."
}

& .\.venv\Scripts\mos.exe doctor
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
