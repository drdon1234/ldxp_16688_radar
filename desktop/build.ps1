$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Get-Command python -ErrorAction Stop | Out-Null
python -m venv '.build-env'
if ($LASTEXITCODE -ne 0) { throw '创建构建环境失败' }
& '.build-env/Scripts/python.exe' -m pip install -r 'requirements.txt'
if ($LASTEXITCODE -ne 0) { throw '安装依赖失败' }
& '.build-env/Scripts/python.exe' 'build.py'
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
