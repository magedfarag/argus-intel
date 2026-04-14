#Requires -Version 5.1
<#
.SYNOPSIS
    Configures QMD collections and context for the watheq-delivery governance workspace.

.DESCRIPTION
    Registers all five knowledge-base collections with the QMD local search index,
    attaches contextual metadata so LLM re-ranking produces governance-aware results,
    and optionally generates vector embeddings.

    Run this script once after cloning the repository, and again whenever the
    collection structure changes. It is idempotent — re-running skips already-
    registered collections.

.PARAMETER RepoRoot
    Absolute path to the watheq-delivery repository root.
    Defaults to the parent directory of this script.

.PARAMETER SkipEmbed
    When set, skips 'qmd embed' after collection setup.
    Useful in CI or air-gapped environments where GGUF models are not available.

.PARAMETER Force
    When set, removes and re-adds each collection even if it already exists.

.EXAMPLE
    .\Setup-QmdCollections.ps1

.EXAMPLE
    .\Setup-QmdCollections.ps1 -SkipEmbed

.EXAMPLE
    .\Setup-QmdCollections.ps1 -Force
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter()]
    [ValidateNotNullOrEmpty()]
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),

    [Parameter()]
    [switch]$SkipEmbed,

    [Parameter()]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:XDG_CACHE_HOME = 'C:\tmp\.cache'

# Suppress Node.js experimental JSON module warning emitted by QMD
$env:NODE_NO_WARNINGS = '1'

#region --- helpers -----------------------------------------------------------

function Write-Step {
    param([string]$Message)
    Write-Host "  >> $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "  OK $Message" -ForegroundColor Green
}

function Format-CommandToken {
    param([Parameter(Mandatory)][string]$Token)

    if ($Token -match '\s') {
        return "'" + ($Token -replace "'", "''") + "'"
    }

    return $Token
}

function Resolve-QmdCli {
    $runningOnWindows = $env:OS -eq 'Windows_NT'
    $qmdCommands = @(Get-Command qmd -All -ErrorAction SilentlyContinue)

    if (-not $runningOnWindows) {
        if (-not $qmdCommands) {
            throw 'qmd is not found on PATH. Install it with: npm install -g @tobilu/qmd'
        }

        return [PSCustomObject]@{
            Executable   = 'qmd'
            PrefixArgs   = @()
            DisplayLabel = 'qmd'
            ManualPrefix = 'qmd'
        }
    }

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
        throw 'node is not found on PATH. Install Node.js 22+ and then install qmd with: npm install -g @tobilu/qmd'
    }

    $candidateEntrypoints = New-Object System.Collections.Generic.List[string]

    foreach ($qmdCommand in $qmdCommands) {
        if (-not $qmdCommand.Path) { continue }

        $commandDir = Split-Path -Parent $qmdCommand.Path
        $candidateEntrypoints.Add((Join-Path $commandDir 'node_modules\@tobilu\qmd\dist\cli\qmd.js'))

        if ((Split-Path -Leaf $commandDir) -eq 'bin') {
            $packageRoot = Split-Path -Parent $commandDir
            $candidateEntrypoints.Add((Join-Path $packageRoot 'dist\cli\qmd.js'))
        }
    }

    if ($env:APPDATA) {
        $candidateEntrypoints.Add((Join-Path $env:APPDATA 'npm\node_modules\@tobilu\qmd\dist\cli\qmd.js'))
    }

    $qmdEntrypoint = $candidateEntrypoints |
        Select-Object -Unique |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1

    if (-not $qmdEntrypoint) {
        throw 'qmd is installed, but its CLI entrypoint could not be located. Reinstall it with: npm install -g @tobilu/qmd'
    }

    return [PSCustomObject]@{
        Executable   = $nodeCommand.Path
        PrefixArgs   = @($qmdEntrypoint)
        DisplayLabel = "node $qmdEntrypoint"
        ManualPrefix = "$(Format-CommandToken $nodeCommand.Path) $(Format-CommandToken $qmdEntrypoint)"
    }
}

function Invoke-Qmd {
    [CmdletBinding()]
    param([string[]]$Arguments)

    $commandArgs = @()
    $commandArgs += $script:QmdCli.PrefixArgs
    $commandArgs += $Arguments

    $output = & $script:QmdCli.Executable @commandArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$($script:QmdCli.DisplayLabel) $($Arguments -join ' ') failed (exit $LASTEXITCODE): $output"
    }

    return $output
}

function Get-ExistingCollectionNames {
    $raw = Invoke-Qmd @('collection', 'list')

    $names = foreach ($line in $raw) {
        # Current output looks like: "governance-docs (qmd://governance-docs/)"
        if ($line -match '^(?<Name>[A-Za-z0-9][A-Za-z0-9._-]*)\s+\(qmd://') {
            $Matches.Name
            continue
        }

        # Older output looked like: "  governance-docs   path/to/folder   5 docs"
        if ($line -match '^\s+(?<Name>\S+)\s{2,}') {
            $Matches.Name
        }
    }

    return @($names | Select-Object -Unique)
}

#endregion

#region --- preflight ---------------------------------------------------------

Write-Host ''
Write-Host 'QMD Collection Setup — Watheq Delivery Governance' -ForegroundColor White
Write-Host ('=' * 52) -ForegroundColor DarkGray
Write-Host ''

$script:QmdCli = Resolve-QmdCli

Write-Step "Repository root: $RepoRoot"
Write-Step "QMD CLI: $($script:QmdCli.DisplayLabel)"

#endregion

#region --- collection definitions -------------------------------------------

$Collections = @(
    [PSCustomObject]@{
        Name    = 'governance-docs'
        Path    = Join-Path $RepoRoot 'docs'
        Context = 'Governance architecture, workflow design, and implementation documentation for the Watheq Delivery Governance system.'
    }
    [PSCustomObject]@{
        Name    = 'wiki'
        Path    = Join-Path $RepoRoot 'wiki-seed'
        Context = 'Wiki seed content: user guides, onboarding pages, and governance reference articles.'
    }
    [PSCustomObject]@{
        Name    = 'reports'
        Path    = Join-Path $RepoRoot 'reports'
        Context = 'Traceability reports, retention checks, dashboard KPIs, and audit-pack indexes generated by the governance system.'
    }
    [PSCustomObject]@{
        Name    = 'templates'
        Path    = Join-Path $RepoRoot 'templates'
        Context = 'Work-item templates, governance document templates, and report templates used across the project.'
    }
    [PSCustomObject]@{
        Name    = 'samples'
        Path    = Join-Path $RepoRoot 'samples'
        Context = 'Sample scenarios (feature release, hotfix, rollback, security patch, etc.) with evidence packages and configuration examples.'
    }
)

#endregion

#region --- register collections ---------------------------------------------

$existingNames = Get-ExistingCollectionNames

foreach ($collection in $Collections) {
    if (-not (Test-Path -LiteralPath $collection.Path)) {
        Write-Warning "Path does not exist, skipping '$($collection.Name)': $($collection.Path)"
        continue
    }

    if ($existingNames -contains $collection.Name) {
        if ($Force) {
            Write-Step "Removing existing collection '$($collection.Name)' (Force)..."
            if ($PSCmdlet.ShouldProcess($collection.Name, 'Remove QMD collection')) {
                Invoke-Qmd @('collection', 'remove', $collection.Name) | Out-Null
            }
        }
        else {
            Write-Success "Collection '$($collection.Name)' already registered — skipping (use -Force to re-add)"
            continue
        }
    }

    Write-Step "Adding collection '$($collection.Name)' → $($collection.Path)"
    if ($PSCmdlet.ShouldProcess($collection.Name, 'Add QMD collection')) {
        try {
            Invoke-Qmd @('collection', 'add', $collection.Path, '--name', $collection.Name) | Out-Null
            Write-Success "Collection '$($collection.Name)' added"
        }
        catch {
            if (-not $Force -and $_.Exception.Message -match "Collection '$([regex]::Escape($collection.Name))' already exists") {
                Write-Success "Collection '$($collection.Name)' already registered — skipping"
                continue
            }

            throw
        }
    }
}

#endregion

#region --- attach context metadata ------------------------------------------

Write-Host ''
Write-Step 'Attaching context metadata to all collections...'

foreach ($collection in $Collections) {
    if (-not (Test-Path -LiteralPath $collection.Path)) { continue }

    $virtualPath = "qmd://$($collection.Name)"
    if ($PSCmdlet.ShouldProcess($virtualPath, 'Set QMD context')) {
        Invoke-Qmd @('context', 'add', $virtualPath, $collection.Context) | Out-Null
        Write-Success "Context set for $virtualPath"
    }
}

# Global context: helps re-ranker understand the overall knowledge base
$globalContext = 'External customer-vendor delivery governance system built on Azure DevOps Server 2022 on-premises. Covers process customization, traceability, retention policies, and audit compliance.'
if ($PSCmdlet.ShouldProcess('/', 'Set QMD global context')) {
    Invoke-Qmd @('context', 'add', '/', $globalContext) | Out-Null
    Write-Success 'Global context set'
}

#endregion

#region --- update index (scan filesystem) -----------------------------------

Write-Host ''
Write-Step 'Updating document index (scanning filesystem)...'
if ($PSCmdlet.ShouldProcess('all collections', 'qmd update')) {
    $updateOutput = Invoke-Qmd @('update')
    $updateOutput | Where-Object { $_ -match '\S' } | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
}
Write-Success 'Index updated'

#endregion

#region --- generate embeddings ----------------------------------------------

if (-not $SkipEmbed) {
    Write-Host ''
    Write-Step 'Generating vector embeddings (first run downloads ~300 MB GGUF model)...'
    Write-Host '     This may take several minutes on first run.' -ForegroundColor DarkYellow
    if ($PSCmdlet.ShouldProcess('all collections', 'qmd embed')) {
        $embedOutput = Invoke-Qmd @('embed')
        $embedOutput | Where-Object { $_ -match '\S' } | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }
    }
    Write-Success 'Embeddings generated'
}
else {
    Write-Warning "Skipping embedding generation (-SkipEmbed). Run $($script:QmdCli.ManualPrefix) embed manually before using semantic or hybrid search."
}

#endregion

#region --- status summary ---------------------------------------------------

Write-Host ''
Write-Step 'Index status:'
Invoke-Qmd @('status') | ForEach-Object { Write-Host "     $_" -ForegroundColor DarkGray }

Write-Host ''
Write-Host '================================================================' -ForegroundColor DarkGray
Write-Host ' QMD setup complete. Try:' -ForegroundColor White
Write-Host "   $($script:QmdCli.ManualPrefix) query ""delivery governance process""" -ForegroundColor Yellow
Write-Host "   $($script:QmdCli.ManualPrefix) query ""retention policy"" -c reports" -ForegroundColor Yellow
Write-Host "   $($script:QmdCli.ManualPrefix) query ""hotfix scenario""  -c samples" -ForegroundColor Yellow
Write-Host '================================================================' -ForegroundColor DarkGray
Write-Host ''

#endregion
