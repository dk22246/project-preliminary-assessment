param(
    [string]$Python = $env:SKILL_PYTHON,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PythonArgs
)

$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONUTF8 = "1"

$prefix = @()
if ($Python) {
    $executable = $Python
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $executable = "python"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $executable = "py"
    $prefix = @("-3")
}
else {
    Write-Error "Python 3 was not found. Install it or set -Python / SKILL_PYTHON to python.exe."
    exit 127
}

& $executable @prefix -X utf8 @PythonArgs
exit $LASTEXITCODE
