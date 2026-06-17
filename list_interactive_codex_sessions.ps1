param(
    [string]$Root = "$env:USERPROFILE\.codex\sessions",
    [int]$Limit = 50
)

$ErrorActionPreference = "Stop"

Get-ChildItem -Path $Root -Recurse -File -Filter "rollout-*.jsonl" |
    ForEach-Object {
        try {
            $first = Get-Content -LiteralPath $_.FullName -TotalCount 1
            if (-not $first) {
                return
            }

            $obj = $first | ConvertFrom-Json
            $payload = $obj.payload

            $source = $payload.source
            $originator = $payload.originator
            $cwd = $payload.cwd

            $sourceText = if ($source -is [string]) {
                $source
            } elseif ($null -eq $source) {
                "<none>"
            } else {
                $source | ConvertTo-Json -Compress
            }

            $originText = if ($originator -is [string]) {
                $originator
            } elseif ($null -eq $originator) {
                "<none>"
            } else {
                $originator | ConvertTo-Json -Compress
            }

            $cwdText = if ($cwd -is [string]) {
                $cwd
            } elseif ($null -eq $cwd) {
                "<none>"
            } else {
                $cwd | ConvertTo-Json -Compress
            }

            $isInteractive =
                $sourceText -eq "vscode" -or
                $originText -eq "codex_vscode" -or
                $originText -eq "Codex Desktop"

            if ($isInteractive) {
                [pscustomobject]@{
                    Timestamp  = $obj.timestamp
                    Source     = $sourceText
                    Originator = $originText
                    Cwd        = $cwdText
                    File       = $_.FullName
                }
            }
        } catch {
            # Einzelne defekte oder inkompatible Session-Dateien werden übersprungen.
        }
    } |
    Sort-Object Timestamp -Descending |
    Select-Object -First $Limit |
    Format-Table -AutoSize
