$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voices = $speaker.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo }
    $voices | Select-Object Name, Culture | Format-Table
    $russian = $voices | Where-Object { $_.Culture.Name -eq 'ru-RU' } | Select-Object -First 1
    if (-not $russian) { throw 'No Russian TTS voice installed.' }
    $speaker.SelectVoice($russian.Name)
    $sampleDir = Join-Path $PSScriptRoot '..\data'
    New-Item -ItemType Directory -Path $sampleDir -Force | Out-Null
    $speaker.SetOutputToWaveFile((Join-Path $sampleDir 'russian-sample.wav'))
    $text = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'sample-text.txt') -Raw -Encoding UTF8
    $speaker.Speak($text)
} finally {
    $speaker.Dispose()
}
