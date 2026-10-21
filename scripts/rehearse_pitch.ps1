param([ValidateSet("v3")][string]$Version = "v3")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pitchInput = Join-Path $projectRoot "data\rehearsal\$Version\pitch.txt"
$pitchOutput = Join-Path $projectRoot "data\rehearsal\$Version\pitch.wav"
if (-not (Test-Path -LiteralPath $pitchInput)) { throw "Run scripts\prepare_rehearsal.py first." }
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice("Microsoft Irina Desktop")
    $speaker.Rate = 0
    $speaker.SetOutputToWaveFile($pitchOutput)
    $speaker.Speak([System.IO.File]::ReadAllText($pitchInput, [System.Text.Encoding]::UTF8))
    $speaker.SetOutputToNull()
} finally { $speaker.Dispose() }
Write-Output $pitchOutput
