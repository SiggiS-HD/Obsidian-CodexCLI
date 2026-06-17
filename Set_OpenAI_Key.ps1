<#
.SYNOPSIS
  Setzt OPENAI_API_KEY fuer die aktuelle Session und optional dauerhaft (User-Umgebung).

.DESCRIPTION
  Dieses Skript hilft beim schnellen Setup fuer SAVE_AS .png.
  Standardverhalten:
  - setzt OPENAI_API_KEY in der aktuellen PowerShell-Session
  - speichert OPENAI_API_KEY dauerhaft per setx fuer den aktuellen Benutzer

.PARAMETER ApiKey
  Optionaler API-Key. Wenn nicht angegeben, wird interaktiv gefragt.

.PARAMETER SessionOnly
  Setzt OPENAI_API_KEY nur fuer die aktuelle Session, ohne setx.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Set_OpenAI_Key.ps1"

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Set_OpenAI_Key.ps1" -SessionOnly

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Set_OpenAI_Key.ps1" -ApiKey "sk-proj-..."
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)]
  [string]$ApiKey,

  [Parameter(Mandatory = $false)]
  [switch]$SessionOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-PlainTextFromSecureString {
  param(
    [Parameter(Mandatory = $true)]
    [System.Security.SecureString]$SecureString
  )

  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
  try {
    return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  }
  finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  }
}

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
  $secure = Read-Host "OpenAI API Key eingeben (wird nicht angezeigt)" -AsSecureString
  $ApiKey = Get-PlainTextFromSecureString -SecureString $secure
}

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
  throw "Kein API-Key angegeben."
}

$env:OPENAI_API_KEY = $ApiKey
Write-Host "[CodexCLI] OPENAI_API_KEY fuer aktuelle Session gesetzt."

if (-not $SessionOnly) {
  setx OPENAI_API_KEY "$ApiKey" | Out-Null
  Write-Host "[CodexCLI] OPENAI_API_KEY dauerhaft fuer Benutzer gespeichert (setx)."
  Write-Host "[CodexCLI] Hinweis: Obsidian/Terminal neu starten, damit der neue Wert ueberall wirksam ist."
}
else {
  Write-Host "[CodexCLI] SessionOnly aktiv: kein setx ausgefuehrt."
}
