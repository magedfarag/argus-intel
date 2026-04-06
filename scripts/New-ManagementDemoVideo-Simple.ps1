#Requires -Version 5.1
<#
.SYNOPSIS
    Demo video generator for ARGUS Maritime Intelligence Platform.
.DESCRIPTION
    Records a fully narrated, 10-minute cinematic walkthrough of ARGUS.
    Uses external HTML/JS templates and a four-step pipeline:
      1. Generate TTS narration MP3s (Edge Neural TTS — en-US-AndrewNeural)
      2. Build a Playwright automation script; scene duration = TTS duration + 2 s max-silence trail
      3. Record video with Playwright navigating the live ARGUS app at localhost:5173
      4. Per-scene adelay audio sync, narration mix, then ffmpeg merge into final MP4

    SILENCE RULE: no scene may have more than 2 seconds of audio silence.
    Every scene including the opening title card carries narration.
    Scene duration is driven by TTS output length, never by a silent floor.

    Scene order (matches docs/demo-recording-script.md, revised 2026-04-09):
      01-opening   : Title card (narrated)
      02-globe     : 3D Globe — Cinematic Open          (hero — 90 s)
      03-animation : Animation Playback — Time Warp     (hero — 60 s)
      04-render    : Render Modes — Eyes of the Operator (35 s)
      05-platform  : Platform Home & Interface Orientation (30 s)
      06-zones     : Zones — Define an Area of Interest  (40 s)
      07-darkships : Dark Ships — AIS Gap Detection      (45 s)
      08-vessel    : Vessel Profile Modal — Sanctions    (35 s)
      09-briefing  : Briefing — AI Intelligence Assessment (40 s)
      10-routes    : Routes — Chokepoint Monitoring      (30 s)
      11-signals   : Signals & Intel — Analytics Montage (50 s)
      12-cases     : Cases — Investigation Workflow      (40 s)
      13-showcase  : Panel Rapid Showcase                (60 s)
      14-closing   : Closing Summary Card                (25 s)

.PARAMETER ShowBrowser
    Launch the browser in headed (visible) mode for debugging. Default is headless.
.PARAMETER SkipCapture
    Skip the Playwright recording step. Useful to regenerate narration only.
.PARAMETER SkipVoice
    Skip TTS generation. Uses a 6 s default per scene. Useful to re-run captures.
.PARAMETER AppUrl
    Base URL of the running ARGUS frontend. Defaults to http://localhost:5173.
.EXAMPLE
    .\scripts\New-ManagementDemoVideo-Simple.ps1
    .\scripts\New-ManagementDemoVideo-Simple.ps1 -ShowBrowser
    .\scripts\New-ManagementDemoVideo-Simple.ps1 -SkipVoice -SkipCapture
    .\scripts\New-ManagementDemoVideo-Simple.ps1 -AppUrl 'http://192.168.1.10:5173'
#>
[CmdletBinding()]
param(
    [switch]$ShowBrowser,
    [switch]$SkipCapture,
    [switch]$SkipVoice,
    [string]$AppUrl = 'http://localhost:5173'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot     = (Resolve-Path "$PSScriptRoot\..").Path
$demoRoot     = Join-Path $repoRoot 'demo'
$recordingDir = Join-Path $demoRoot 'recording'
$templatesDir = Join-Path $demoRoot 'templates'
$audioDir     = Join-Path $demoRoot 'audio'

foreach ($dir in @($recordingDir, $templatesDir, $audioDir)) {
    if (-not (Test-Path $dir)) { New-Item $dir -ItemType Directory -Force | Out-Null }
}

Write-Host '=== ARGUS Maritime Intelligence — Demo Video Generator ===' -ForegroundColor Cyan
Write-Host "App URL: $AppUrl" -ForegroundColor Gray
Write-Host ''

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Ensure ffmpeg is available (install ffmpeg-static via npm locally)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host '[1/4] Checking ffmpeg...' -ForegroundColor Yellow

function Get-FfmpegPath {
    $inPath = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }

    # Check locally installed ffmpeg-static in demo/node_modules
    $localStatic = Join-Path $demoRoot 'node_modules\ffmpeg-static\ffmpeg.exe'
    if (Test-Path $localStatic) { return $localStatic }

    # Ask Node.js
    Push-Location $demoRoot
    try {
        $p = node -e "try{process.stdout.write(require('ffmpeg-static'))}catch(e){}" 2>$null
        if ($p -and (Test-Path $p)) { return $p }
    } finally { Pop-Location }

    return $null
}

$ffmpegPath = Get-FfmpegPath

if (-not $ffmpegPath) {
    Write-Host '  ffmpeg not found — installing ffmpeg-static via npm...' -ForegroundColor Yellow
    Push-Location $demoRoot
    try {
        npm install ffmpeg-static --save-exact --loglevel error 2>&1 | Out-Null
    } finally { Pop-Location }
    $ffmpegPath = Get-FfmpegPath
}

if ($ffmpegPath) {
    Write-Host "  ✓ ffmpeg: $ffmpegPath" -ForegroundColor Green
} else {
    Write-Warning 'ffmpeg unavailable — final MP4 will not be produced'
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Generate TTS narration (Microsoft Mark — male natural voice)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host '[2/4] Generating voice narration...' -ForegroundColor Yellow

# Plain conversational English — en-US-AndrewNeural, natural conversational delivery.
# Commas and sentence structure create breath pauses. No SSML tags needed.
# ── Narration aligned to docs/demo-recording-script.md (revised 2026-04-09) ──
# SILENCE RULE: no audio gap in the final video may exceed 2 seconds.
# Every scene — including the opening title card — has narration.
# Scene duration = TTS duration + 2 s max-silence trail. No silent floors.
# Voice: Edge Neural TTS, en-US-AndrewNeural, ~130 wpm.
$narrationScript = [ordered]@{
    '01-opening'    = 'ARGUS. Maritime intelligence at global scale.'
    '02-globe'      = "ARGUS is a real-time, multi-domain intelligence platform built for the world's most critical maritime environments. What you're seeing is a live operational picture of the Strait of Hormuz — twelve miles wide at its narrowest, carrying twenty percent of the world's oil supply through every twenty-four hours. ARGUS fuses satellite imagery, automatic identification system feeds, open-source intelligence, and airspace data into a single, persistent command view. Every vessel you see is tracked. Every gap in their signal is flagged. And every threat assessment updates in real time."
    '03-animation'  = "The ARGUS Replay engine reconstructs any historical time window as a precision intelligence film. Here we're watching thirty hours of strait traffic compressed in real time. Every position report from every vessel, every second of their journey, rendered exactly as it happened. Watch what occurs when we accelerate the clock — four times faster — the traffic separation scheme becomes visible as a pattern, inbound and outbound lanes separating automatically under the maritime rules of the road. ARGUS doesn't just archive data. It lets your analysts replay, pause, and interrogate history — frame by frame."
    '04-render'     = "ARGUS doesn't operate in a single spectrum. The platform supports four display modes — standard daylight, low-light maritime dusk, night-vision green for twenty-four-hour operations, and thermal overlay for heat-signature analysis. Your operators see what the moment demands — and switch modes instantly."
    '05-platform'   = "The ARGUS interface is built around one principle — every piece of intelligence, one screen. The persistent timeline along the bottom tracks every event from every source as colored dots across your entire operational window. Thirteen analysis panels extend from the left rail. Everything stays in sync as you move through time."
    '06-zones'      = "Analysis begins by defining an area of interest — your operational geofence. Draw a polygon or bounding box on the globe. Name it. Save it. From that moment, every data feed, every detection, every alert is filtered and correlated to that zone automatically. One zone can span twelve miles of a chokepoint or the entire Arabian Sea — ARGUS scales to the mission."
    '07-darkships'  = "The Dark Ships module continuously monitors for AIS transmission gaps — the signature of vessels attempting to evade tracking. When a vessel goes dark, ARGUS measures the gap duration, calculates the maximum distance it could have traveled, and cross-references its last registry record against OFAC sanctions lists. The three vessels you're seeing flagged here — including one with a forty-eight-hour transmission gap and a position jump of over four hundred kilometers — are all active detection cases."
    '08-vessel'     = "Every vessel in ARGUS carries a full intelligence profile. One click surfaces IMO registry data, current ownership, flag state, gross tonnage, and — critically — sanctions status cross-referenced against OFAC's SDN list. This vessel is flagged as OFAC-sanctioned, with a forty-eight hour dark gap and a documented position jump consistent with a ship-to-ship transfer. The kind of evidence that supports a compliance brief or a flag-state notification in under sixty seconds."
    '09-briefing'   = "This is the ARGUS Intelligence Briefing — a continuously updated commander's summary generated from every active feed. Dark vessel counts. Sanctioned actors. Active anomalies. Key findings translated from raw data into plain language. A new analyst joining an operation gets full situational awareness in under a minute — without touching a filter or writing a query."
    '10-routes'     = "The Routes module monitors the world's strategic maritime chokepoints in real time. Current threat level — CRITICAL at Hormuz. Seventeen million barrels of oil flow through daily. Vessel count trending upward. These are the five maritime arteries that move forty percent of global seaborne trade — and ARGUS watches all of them simultaneously."
    '11-signals'    = "Signals aggregates every raw intelligence event from every connected source into a single searchable stream — AIS, airspace, open-source media, and ACLED conflict data — each tagged with a machine-confidence score. The Intel module runs automated change detection across multi-temporal satellite imagery — detecting construction, vessel movements, and infrastructure changes. Each detection carries an AI-generated rationale. Analysts confirm or dismiss with a single click — creating an auditable intelligence record."
    '12-cases'      = "Every detection, every dark ship, every confirmed change feeds into the Cases module — a structured investigation workflow designed for the full analyst lifecycle. Cases are traceable, shareable, and exportable. From the moment an anomaly is detected to the moment a brief reaches a decision-maker, every action is logged."
    '13-showcase'   = "Diff places any two satellite acquisitions side by side — measuring days, cloud cover, and the delta between them. Cameras aggregates every registered sensor feed — optical, thermal, night-vision, SAR — all time-synced to the live playback clock. The Timeline strip at the bottom anchors every event across every source in a single visual timeline. Extract exports any dataset in open formats — GeoJSON or CSV — in seconds. And Status gives operators a live health check on every infrastructure component, every provider, every data connector."
    '14-closing'    = "ARGUS — persistent, multi-domain intelligence at global scale. Thirteen integrated modules. Eleven live data connectors. Real-time and historical analysis in one operational picture."
}

function Get-WavDurationMs {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    for ($i = 12; $i -lt ($bytes.Length - 8); $i++) {
        if ($bytes[$i] -eq 0x64 -and $bytes[$i+1] -eq 0x61 -and
            $bytes[$i+2] -eq 0x74 -and $bytes[$i+3] -eq 0x61) {
            $dataSize      = [BitConverter]::ToInt32($bytes, $i + 4)
            $sampleRate    = [BitConverter]::ToInt32($bytes, 24)
            $channels      = [BitConverter]::ToInt16($bytes, 22)
            $bitsPerSample = [BitConverter]::ToInt16($bytes, 34)
            if ($sampleRate -gt 0 -and $channels -gt 0 -and $bitsPerSample -gt 0) {
                return [int](($dataSize / ($sampleRate * $channels * ($bitsPerSample / 8))) * 1000)
            }
        }
    }
    return 5000
}

$sceneDurations = [ordered]@{}   # key -> narration duration in ms

if (-not $SkipVoice) {
    $ttsGenScript  = Join-Path $demoRoot 'tts-generate.js'
    if (-not (Test-Path $ttsGenScript)) {
        Write-Error "tts-generate.js not found at $($ttsGenScript)"
    }

    # Auto-install msedge-tts if absent (installs into demo/node_modules)
    $edgeTtsMod = Join-Path $demoRoot 'node_modules\msedge-tts'
    if (-not (Test-Path $edgeTtsMod)) {
        Write-Host '  Installing msedge-tts...' -ForegroundColor Yellow
        Push-Location $demoRoot
        try {
            # Ensure demo/ has a package.json so npm install targets it correctly
            if (-not (Test-Path (Join-Path $demoRoot 'package.json'))) {
                npm init -y 2>&1 | Out-Null
            }
            npm install msedge-tts --loglevel error 2>&1 | Out-Null
        } finally { Pop-Location }
    }

    # Write scenes JSON consumed by the Node TTS script
    $scenesJsonPath = Join-Path $demoRoot 'tts-scenes.json'
    $scenesObj = [ordered]@{}
    foreach ($k in $narrationScript.Keys) { $scenesObj[$k] = $narrationScript[$k] }
    $scenesObj | ConvertTo-Json | Set-Content $scenesJsonPath -Encoding UTF8

    Write-Host '  Voice : en-US-AndrewNeural (Edge Neural TTS)' -ForegroundColor Cyan
    Push-Location $repoRoot
    try {
        $ttsLines = [System.Collections.Generic.List[string]]::new()
        node $ttsGenScript $scenesJsonPath $audioDir 2>&1 | ForEach-Object {
            $ttsLines.Add("$_")
            Write-Host "  $_" -ForegroundColor Gray
        }
        if ($LASTEXITCODE -ne 0) { throw "TTS generation failed (exit $LASTEXITCODE)" }
        # Parse DURATION:key:ms stdout lines
        foreach ($line in $ttsLines) {
            if ($line -match '^DURATION:([^:]+):(\.?\d+)$') {
                $sceneDurations[$Matches[1]] = [int]$Matches[2]
            }
        }
    } finally { Pop-Location }

    # Fallback: read any missing durations from WAV headers
    foreach ($key in $narrationScript.Keys) {
        if (-not $sceneDurations.Contains($key)) {
            $wavPath = Join-Path $audioDir "$key.wav"
            if (Test-Path $wavPath) {
                $sceneDurations[$key] = Get-WavDurationMs -Path $wavPath
                Write-Host "  ✓ $key  $($sceneDurations[$key])ms (WAV header)" -ForegroundColor Green
            } else {
                $sceneDurations[$key] = 6000
                Write-Warning "WAV missing for $key — using 6 s default"
            }
        }
    }
    # Print confirmed durations
    foreach ($key in $sceneDurations.Keys) {
        Write-Host "  ✓ $key  $($sceneDurations[$key])ms" -ForegroundColor Green
    }
} else {
    # -SkipVoice: read real durations from existing MP3 files via ffprobe.
    # Falls back to 6 s only when an MP3 is genuinely absent.
    Write-Host '  (SkipVoice — reading durations from existing MP3s)' -ForegroundColor Gray
    foreach ($key in $narrationScript.Keys) {
        $mp3Path = Join-Path $audioDir "$key.mp3"
        if ($ffmpegPath -and (Test-Path $mp3Path)) {
            $ffprobePath = Join-Path (Split-Path $ffmpegPath) 'ffprobe.exe'
            if (Test-Path $ffprobePath) {
                $raw = & $ffprobePath -v quiet -show_entries format=duration `
                           -of default=noprint_wrappers=1:nokey=1 $mp3Path 2>&1
                $secs = [double]0
                if ([double]::TryParse($raw, [ref]$secs) -and $secs -gt 0) {
                    $sceneDurations[$key] = [int]($secs * 1000)
                    Write-Host "  ✓ $key  $($sceneDurations[$key])ms (ffprobe)" -ForegroundColor Green
                    continue
                }
            }
        }
        # Fallback
        $sceneDurations[$key] = 6000
        Write-Warning "$key MP3 not found or ffprobe failed — using 6 s default"
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Build Playwright script (scene timing = narration + 2 s trail buffer)
# ─────────────────────────────────────────────────────────────────────────────
Write-Host '[3/4] Building Playwright script...' -ForegroundColor Yellow

# Maps narration key → Playwright SCENE_MS property name.
# SILENCE RULE: scene hold = narrationMs + 2000 ms (2 s tail, hard cap).
# No silent floors — narration length drives all scene durations.
# Playwright interaction pacing reference (approximate narration durations):
#   01-opening     ~3 s  (title card)        02-globe      ~60 s  (3D hero)
#   03-animation   ~52 s (replay hero)       04-render     ~24 s
#   05-platform    ~24 s                     06-zones      ~28 s
#   07-darkships   ~36 s                     08-vessel     ~36 s
#   09-briefing    ~29 s                     10-routes     ~22 s
#   11-signals     ~43 s                     12-cases      ~29 s
#   13-showcase    ~38 s                     14-closing    ~13 s
$sceneKeyMap = [ordered]@{
    '01-opening'   = 'opening'
    '02-globe'     = 'globe'
    '03-animation' = 'animation'
    '04-render'    = 'renderModes'
    '05-platform'  = 'platform'
    '06-zones'     = 'zones'
    '07-darkships' = 'darkShips'
    '08-vessel'    = 'vesselProfile'
    '09-briefing'  = 'briefing'
    '10-routes'    = 'routes'
    '11-signals'   = 'signalsIntel'
    '12-cases'     = 'cases'
    '13-showcase'  = 'showcase'
    '14-closing'   = 'closing'
}

# Scene duration = TTS duration + 2 s max-silence trail (strictly enforced).
# Min floor of 3000 ms guards against TTS failures returning 0 ms duration.
$silenceTrailMs = 2000
$sceneTimingPairs = $sceneKeyMap.GetEnumerator() | ForEach-Object {
    $narKey  = $_.Key
    $jsKey   = $_.Value
    $durMs   = if ($sceneDurations.Contains($narKey)) { $sceneDurations[$narKey] } else { 4000 }
    $totalMs = [Math]::Max(3000, $durMs) + $silenceTrailMs
    "`"$jsKey`": $totalMs"
}
$sceneTimingJson = '{ ' + ($sceneTimingPairs -join ', ') + ' }'

$playwrightTemplate = Get-Content (Join-Path $templatesDir 'playwright-template.js') -Raw

# Copy HTML card assets alongside the generated script so the template can fs.readFileSync them
Copy-Item (Join-Path $templatesDir 'opening-scene.html') (Join-Path $recordingDir 'opening-scene.html') -Force
Copy-Item (Join-Path $templatesDir 'closing-scene.html') (Join-Path $recordingDir 'closing-scene.html') -Force

$playwrightScript = $playwrightTemplate.Replace('{{APP_URL}}', $AppUrl)
$playwrightScript = $playwrightScript.Replace('{{HEADLESS}}', $(if ($ShowBrowser) { 'false' } else { 'true' }))
$playwrightScript = $playwrightScript.Replace('{{SCENE_TIMING_JSON}}', $sceneTimingJson)

$playwrightScriptPath = Join-Path $recordingDir 'record-demo-simple.js'
Set-Content -Path $playwrightScriptPath -Value $playwrightScript -Encoding UTF8
Write-Host "  ✓ Script : $playwrightScriptPath" -ForegroundColor Green
Write-Host "  ✓ Timing : $sceneTimingJson" -ForegroundColor Gray

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Record video, build narration track, merge into final MP4
# ─────────────────────────────────────────────────────────────────────────────
Write-Host '[4/4] Recording...' -ForegroundColor Yellow

if (-not $SkipCapture) {
    Push-Location $repoRoot
    $outputLines = [System.Collections.Generic.List[string]]::new()
    try {
        # Capture stdout+stderr so we can parse [NARRATE:key:ms] timestamps
        node $playwrightScriptPath 2>&1 | ForEach-Object {
            $line = "$_"
            $outputLines.Add($line)
            Write-Host "  $line" -ForegroundColor Gray
        }
        if ($LASTEXITCODE -ne 0) { throw "Playwright exited $LASTEXITCODE" }
        Write-Host '  ✓ Video recorded' -ForegroundColor Green
    } finally { Pop-Location }

    # Persist NARRATE timestamps so the merge phase can run independently
    # (supports re-run with -SkipCapture after a successful recording).
    $syncCachePath = Join-Path $demoRoot 'audio-sync.json'
    $narrateTsRaw = [ordered]@{}
    foreach ($line in $outputLines) {
        if ($line -match '\[NARRATE:(\w+):(\d+)\]') {
            $narrateTsRaw[$Matches[1]] = [int]$Matches[2]
        }
    }
    if ($narrateTsRaw.Count -gt 0) {
        $narrateTsRaw | ConvertTo-Json | Set-Content $syncCachePath -Encoding UTF8
        Write-Host "  ✓ Sync timestamps saved: $syncCachePath" -ForegroundColor Gray
    }
}

$rawVideoPath = Join-Path $demoRoot 'recording.webm'

# ── Audio sync: runs whenever raw video + MP3s exist (independent of -SkipCapture/-SkipVoice)
$mp3Count = (Get-ChildItem $audioDir -Filter '*.mp3' -ErrorAction SilentlyContinue).Count
if ($ffmpegPath -and $mp3Count -gt 0 -and (Test-Path $rawVideoPath)) {
    Write-Host '  Parsing scene timestamps...' -ForegroundColor Yellow

    # Load from cache file (written during recording) or fall back to 0 delay
    $syncCachePath = Join-Path $demoRoot 'audio-sync.json'
    $narrateTs     = [ordered]@{}
    if (Test-Path $syncCachePath) {
        $cached = Get-Content $syncCachePath -Raw | ConvertFrom-Json
        $cached.PSObject.Properties | ForEach-Object { $narrateTs[$_.Name] = [int]$_.Value }
        Write-Host "  ✓ Loaded sync timestamps from cache ($($narrateTs.Count) scenes)" -ForegroundColor Gray
    }

    if ($narrateTs.Count -eq 0) {
        Write-Warning 'No NARRATE timestamps found — falling back to 0 delay'
        foreach ($jsKey in $sceneKeyMap.Values) { $narrateTs[$jsKey] = 0 }
    }

    foreach ($pair in $narrateTs.GetEnumerator()) {
        Write-Host "  ✓ [NARRATE] $($pair.Key) = $($pair.Value) ms" -ForegroundColor Cyan
    }

    Write-Host '  Applying per-scene delays and mixing...' -ForegroundColor Yellow

    $delayedWavPaths = [System.Collections.Generic.List[string]]::new()

    foreach ($key in $sceneKeyMap.Keys) {
        $jsKey    = $sceneKeyMap[$key]
        $srcAudio = Join-Path $audioDir "$key.mp3"
        $delWav   = Join-Path $audioDir "$key-delayed.wav"
        $delayMs  = if ($narrateTs.Contains($jsKey)) { $narrateTs[$jsKey] } else { 0 }

        # Decode MP3, convert to stereo 44100 Hz, apply scene-start delay
        $null = & $ffmpegPath -y -i $srcAudio -ac 2 -ar 44100 `
                    -af "adelay=${delayMs}ms:all=1" $delWav 2>&1
        if ($LASTEXITCODE -eq 0 -and (Test-Path $delWav)) {
            $delayedWavPaths.Add($delWav)
            Write-Host "  ✓ $key delayed ${delayMs}ms" -ForegroundColor Green
        } else {
            Write-Warning "adelay failed for $key"
        }
    }

    # Mix all delayed clips into one narration track
    $fullNarrationWav = Join-Path $demoRoot 'narration.wav'
    $ninputs          = $delayedWavPaths.Count
    $inputArgs        = $delayedWavPaths | ForEach-Object { "-i"; $_ }
    $null = & $ffmpegPath -y @inputArgs `
                -filter_complex "amix=inputs=${ninputs}:duration=longest:normalize=0" `
                $fullNarrationWav 2>&1

    if ($LASTEXITCODE -eq 0 -and (Test-Path $fullNarrationWav)) {
        Write-Host '  ✓ Narration track mixed' -ForegroundColor Green

        # Calculate content trim point: last NARRATE timestamp + last scene narration +
        # the configured 2 s silence tail. Keep millisecond precision so the final
        # cut does not introduce an extra whole-second silent pad after the narration.
        # Playwright's context.close() appends 2-3 min of blank encoder-finalization
        # frames to the webm; trimming removes them without re-encoding the video stream.
        $lastJsKey      = ($sceneKeyMap.Values | Select-Object -Last 1)   # e.g. "closing"
        $lastNarKey     = ($sceneKeyMap.Keys   | Select-Object -Last 1)   # e.g. "14-closing"
        $lastNarrateMs  = if ($narrateTs.Contains($lastJsKey)) { [int]$narrateTs[$lastJsKey] } else { 0 }
        $lastDurMs      = if ($sceneDurations.Contains($lastNarKey)) { [int]$sceneDurations[$lastNarKey] } else { 6000 }
        $trimMs         = $lastNarrateMs + $lastDurMs + $silenceTrailMs
        $trimSecs       = [string]::Format(
            [System.Globalization.CultureInfo]::InvariantCulture,
            '{0:0.000}',
            ($trimMs / 1000.0)
        )
        Write-Host "  ✓ Trim point: ${trimSecs}s (last NARRATE ${lastNarrateMs}ms + ${lastDurMs}ms narration + ${silenceTrailMs}ms tail)" -ForegroundColor Gray

        # Merge video + narration into final MP4; -t trims encoder-padding blank at end
        $stamp          = Get-Date -Format 'yyyyMMdd-HHmm'
        $finalVideoPath = Join-Path $demoRoot "ARGUS-Demo-$stamp.mp4"
        $null = & $ffmpegPath -y -i $rawVideoPath -i $fullNarrationWav `
                    -t $trimSecs `
                    -c:v libx264 -preset fast -crf 22 `
                    -c:a aac -b:a 128k `
                    -map '0:v:0' -map '1:a:0' `
                    $finalVideoPath 2>&1

        if ($LASTEXITCODE -eq 0 -and (Test-Path $finalVideoPath)) {
            $sizeMB = [Math]::Round((Get-Item $finalVideoPath).Length / 1MB, 1)
            Write-Host ''
            Write-Host '=== Final Output ===' -ForegroundColor Cyan
            Write-Host "  $finalVideoPath ($sizeMB MB, ${trimSecs}s)" -ForegroundColor Green
        } else {
            Write-Warning 'Final MP4 merge failed — raw webm preserved'
        }
    } else {
        Write-Warning 'Narration mix failed — keeping raw webm'
    }
} elseif (-not $ffmpegPath) {
    Write-Host "  Raw video (no ffmpeg): $rawVideoPath" -ForegroundColor Yellow
}

if ($SkipCapture) {
    Write-Host '  (SkipCapture — used existing recording.webm)' -ForegroundColor Gray
}
