# Only remove generated search artifacts from the copied engine, never the source project.
$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
foreach ($engineRelativePath in @('engines/archive/hashcat','dist/K文件处理台/engines/archive/hashcat')) {
$copiedEnginePath = [IO.Path]::GetFullPath((Join-Path $workspacePath $engineRelativePath))
if (-not $copiedEnginePath.StartsWith($workspacePath + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid copied engine path' }
if (-not (Test-Path -LiteralPath $copiedEnginePath)) { continue }
foreach ($item in @(Get-ChildItem -LiteralPath $copiedEnginePath -Force)) {
    if ($item.Name -eq 'cache' -or $item.Name -like '*.outfiles' -or $item.Name -like '*.pid' -or $item.Name -like '*.restore*' -or $item.Name -like '*.potfile') {
        $verifiedPath = [IO.Path]::GetFullPath($item.FullName)
        if (-not $verifiedPath.StartsWith($copiedEnginePath + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid generated artifact path' }
        if ($item.Name -eq 'cache' -or $item.Name -like '*.pid') {
            Remove-Item -LiteralPath $verifiedPath -Recurse -Force
        } else {
            $dataRelative = if ($engineRelativePath.StartsWith('dist/')) { 'dist/K文件处理台/data/archive-engine/历史引擎文件' } else { 'data/archive-engine/历史引擎文件' }
            $backupPath = [IO.Path]::GetFullPath((Join-Path $workspacePath ($dataRelative + '/' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '/' + $item.Name)))
            if (-not $backupPath.StartsWith($workspacePath + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid preservation path' }
            [IO.Directory]::CreateDirectory((Split-Path -Parent $backupPath)) | Out-Null
            Move-Item -LiteralPath $verifiedPath -Destination $backupPath
        }
    }
}
}
Write-Output 'Copied archive engine: personal search artifacts excluded.'
