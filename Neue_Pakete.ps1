<#
.SYNOPSIS
  Installiert/aktualisiert Python-Pakete fuer CodexCLI.

.DESCRIPTION
  Dieses Script ist fuer Setups gedacht, in denen der Obsidian Vault auf einem NAS (UNC) liegt,
  die Python-venv aber lokal auf dem Windows-PC liegt.

  Es nutzt die gleiche venv-Logik wie run_codexcli.cmd:
  - Bei lokalen Repos wird <CODEXCLI_HOME>\.venv bevorzugt.
  - Bei UNC/NAS-Repos wird %LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI\.venv bevorzugt.

.PARAMETER Packages
  Zusaetzliche Pakete, die installiert werden sollen (z.B. "requests", "pydantic==2.7.0").

.PARAMETER RequirementsPath
  Optionaler Pfad zu requirements.txt (Default: <CODEXCLI_HOME>\requirements.txt).

.PARAMETER VenvBase
  Optionaler Name fuer %CODEXCLI_VENV% (Default: Env:CODEXCLI_VENV oder "Siggiverse").

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Neue_Pakete.ps1"

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Neue_Pakete.ps1" -Packages pypdf
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)]
  [string[]]$Packages,

  [Parameter(Mandatory = $false)]
  [string]$RequirementsPath,

  [Parameter(Mandatory = $false)]
  [string]$VenvBase
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-VenvBaseFromRepoPath {
  param(
    [Parameter(Mandatory = $true)]
    [string]$RepoPath
  )

  $repoDir = Split-Path -Path $RepoPath -Leaf
  if ($repoDir -ine "CodexCLI") {
    return $null
  }

  $addonPath = Split-Path -Path $RepoPath -Parent
  if ((Split-Path -Path $addonPath -Leaf) -ine ".AddOn") {
    return $null
  }

  $vaultName = Split-Path -Path (Split-Path -Path $addonPath -Parent) -Leaf
  if ([string]::IsNullOrWhiteSpace($vaultName)) {
    return $null
  }

  return $vaultName
}

$codexCliHome = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($RequirementsPath)) {
  $RequirementsPath = Join-Path $codexCliHome "requirements.txt"
}

if ([string]::IsNullOrWhiteSpace($VenvBase)) {
  $envVenvBase = $env:CODEXCLI_VENV
  $derivedVenvBase = Get-VenvBaseFromRepoPath -RepoPath $codexCliHome

  if ($codexCliHome.StartsWith('\\')) {
    if (-not [string]::IsNullOrWhiteSpace($derivedVenvBase)) {
      $VenvBase = $derivedVenvBase
    } elseif (-not [string]::IsNullOrWhiteSpace($envVenvBase)) {
      $VenvBase = $envVenvBase
    }
  } else {
    if (-not [string]::IsNullOrWhiteSpace($envVenvBase)) {
      $VenvBase = $envVenvBase
    } elseif (-not [string]::IsNullOrWhiteSpace($derivedVenvBase)) {
      $VenvBase = $derivedVenvBase
    }
  }

  if ([string]::IsNullOrWhiteSpace($VenvBase)) {
    $VenvBase = "Siggiverse"
  }
}

$repoVenvPython = Join-Path $codexCliHome ".venv\Scripts\python.exe"
$localVenvPath = Join-Path $env:LOCALAPPDATA (Join-Path $VenvBase "CodexCLI\.venv")
$localVenvPython = Join-Path $localVenvPath "Scripts\python.exe"
$isUncRepo = $codexCliHome.StartsWith('\\')

function New-LocalVenv {
  if (-not (Test-Path $localVenvPython)) {
    New-Item -ItemType Directory -Force -Path $localVenvPath | Out-Null
    python -m venv $localVenvPath
  }

  if (-not (Test-Path $localVenvPython)) {
    throw "Lokale venv wurde erstellt, aber python.exe wurde nicht gefunden: $localVenvPython"
  }

  return $localVenvPython
}

if ($isUncRepo) {
  if (Test-Path $localVenvPython) {
    $pythonExe = $localVenvPython
  } elseif (Test-Path $repoVenvPython) {
    Write-Warning "Repo-.venv auf UNC/NAS gefunden. Lokale venv waere robuster."
    $pythonExe = $repoVenvPython
  } else {
    $pythonExe = New-LocalVenv
  }
} else {
  if (Test-Path $repoVenvPython) {
    $pythonExe = $repoVenvPython
  } elseif (Test-Path $localVenvPython) {
    $pythonExe = $localVenvPython
  } else {
    $pythonExe = New-LocalVenv
  }
}

Write-Host "[CodexCLI] Using Python: $pythonExe"

& $pythonExe -m pip install --upgrade pip

if (Test-Path $RequirementsPath) {
  & $pythonExe -m pip install -r $RequirementsPath
} else {
  Write-Warning "requirements.txt nicht gefunden: $RequirementsPath"
}

if ($Packages -and $Packages.Count -gt 0) {
  & $pythonExe -m pip install @Packages
}

Write-Host "[CodexCLI] Fertig."
