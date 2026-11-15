# Remove explicitly managed obsolete artifacts; preserve all app data first.
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$taskPrefix = $taskRoot + '\'
$script:removed = [Collections.Generic.List[string]]::new()
$script:preserved = [Collections.Generic.List[object]]::new()
$previousRecord = Join-Path $taskRoot 'docs/清理记录-v1.0.0.json'
if (-not (Test-Path -LiteralPath $previousRecord)) { $previousRecord = Join-Path $taskRoot 'docs/清理记录-v0.11.json' }
if (Test-Path -LiteralPath $previousRecord) {
    $previousCleanup = Get-Content -LiteralPath $previousRecord -Raw | ConvertFrom-Json
    if ($previousCleanup.version -eq '1.0.0') { foreach ($entry in $previousCleanup.removed) { $script:removed.Add($entry) } }
    foreach ($entry in $previousCleanup.preserved) {
        if (Test-Path -LiteralPath (Join-Path $taskRoot $entry.destination)) { $script:preserved.Add($entry) }
    }
}

function Assert-WorkspacePath([string]$candidate) {
    $resolved = [IO.Path]::GetFullPath($candidate)
    if (-not $resolved.StartsWith($taskPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing operation outside workspace: $resolved"
    }
    return $resolved
}

function Remove-ManagedPath([string]$candidate) {
    $resolved = Assert-WorkspacePath $candidate
    if (Test-Path -LiteralPath $resolved) {
        $item = Get-Item -LiteralPath $resolved -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Unexpected reparse point: $resolved" }
        Write-Output ('Removing: ' + [IO.Path]::GetRelativePath($taskRoot, $resolved))
        Remove-Item -LiteralPath $resolved -Recurse -Force
        $script:removed.Add([IO.Path]::GetRelativePath($taskRoot, $resolved))
    }
}

function Move-PreservedPath([string]$sourcePath, [string]$destinationPath) {
    $sourceResolved = Assert-WorkspacePath $sourcePath
    $destinationResolved = Assert-WorkspacePath $destinationPath
    if (-not (Test-Path -LiteralPath $sourceResolved)) { return }
    if (Test-Path -LiteralPath $destinationResolved) { throw "Preservation target already exists: $destinationResolved" }
    if ((Get-Item -LiteralPath $sourceResolved -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unexpected reparse point in saved data' }
    $parentPath = Assert-WorkspacePath (Split-Path -Parent $destinationResolved)
    [IO.Directory]::CreateDirectory($parentPath) | Out-Null
    Move-Item -LiteralPath $sourceResolved -Destination $destinationResolved
    $script:preserved.Add(@{source=[IO.Path]::GetRelativePath($taskRoot,$sourceResolved);destination=[IO.Path]::GetRelativePath($taskRoot,$destinationResolved)})
}

$latestData = Join-Path $taskRoot 'dist/K文件处理台/data'
$knownProgramNames = @('_internal','engines','licenses','source','docs','data','格式之间.exe','K文件处理台.exe','README.md','THIRD_PARTY_NOTICES.md','requirements.txt','requirements-lock.txt','LICENSE.txt')
foreach ($obsolete in @(@{path='dist/格式之间';tag='原格式之间'},@{path='release/K文件处理台';tag='原便携解压版'})) {
    $oldPath = Assert-WorkspacePath (Join-Path $taskRoot $obsolete.path)
    if (-not (Test-Path -LiteralPath $oldPath)) { continue }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $origin = $obsolete.tag + '-' + $stamp
    Move-PreservedPath (Join-Path $oldPath 'data/outputs') (Join-Path $latestData ('outputs/历史导入/' + $origin))
    Move-PreservedPath (Join-Path $oldPath 'data') (Join-Path $latestData ('历史数据/' + $origin))
    $oldHashcat = Assert-WorkspacePath (Join-Path $oldPath 'engines/archive/hashcat')
    if (Test-Path -LiteralPath $oldHashcat) {
        foreach ($artifact in @(Get-ChildItem -LiteralPath $oldHashcat -Force)) {
            if ($artifact.Name -like '*.outfiles' -or $artifact.Name -like '*.restore*' -or $artifact.Name -like '*.potfile') {
                Move-PreservedPath $artifact.FullName (Join-Path $latestData ('历史数据/' + $origin + '/引擎断点/' + $artifact.Name))
            }
        }
    }
    foreach ($extra in @(Get-ChildItem -LiteralPath $oldPath -Force)) {
        if ($extra.Name -notin $knownProgramNames) {
            Move-PreservedPath $extra.FullName (Join-Path $latestData ('历史数据/' + $origin + '/额外文件/' + $extra.Name))
        }
    }
    Remove-ManagedPath $oldPath
}

foreach ($relativePath in @('build','Kdebug.spec','release/格式之间-Windows-x64.zip','engines/LibreOffice.msi','engines/pandoc.zip','engines/pandoc-unpack','engines/office-extract.log','__pycache__','.pytest_cache','tests/__pycache__','tools/__pycache__','docs/desktop-release-v11/working','docs/archive-portable-v11/working','docs/archive-source-v11','docs/guide-review-v11')) {
    Remove-ManagedPath (Join-Path $taskRoot $relativePath)
}
foreach ($oldLog in @(Get-ChildItem -LiteralPath $taskRoot -File -Filter '*.log')) { Remove-ManagedPath $oldLog.FullName }

$docsPath = Join-Path $taskRoot 'docs'
$currentDocs = @('screenshots','引擎来源.md','图片引擎来源.md','搜索范围与顺序.md','版本说明-v1.0.0.md','验证-v1.0.0.md','release-validation.json','清理记录-v1.0.0.json')
$oldDocPattern = '^(desktop-v\d+|desktop-release-v0[2345]|frozen-widget-v02-final|native-launch-v0[2345]\.json|portable-legacy-v05\.json|版本说明-v0\.5\.md|验证-v0\.5\.txt|清理记录-v0\.5\.json|portable-final-smoke\.json|portable-test-results\.json|动态预览抽帧-v03\.png|界面-.*\.png|紧凑圆盘-.*|矩形布局-v05-初稿\.png|浏览器测试结果\.html|双模式圆盘-.*|说明简略-v05-初稿\.png|体验表格\.csv|体验文件\.(md|pdf)|验收说明\.md|圆盘动态预览-v0[345]\.gif|圆盘间距-v05-初稿\.png|桌面挂件-v0\.2\.md|K挂件-.*\.png|K圆盘-v03\.png)$'
foreach ($oldDoc in @(Get-ChildItem -LiteralPath $docsPath -Force)) {
    if ($oldDoc.Name -notin $currentDocs -and ($oldDoc.Name -match $oldDocPattern -or $oldDoc.Name -match '^(desktop-release-v11|archive-portable-v11|extra-portable-v11|native-launch-v11\.json|browser-v11|圆盘动态预览-v11\.gif|光圈动画记录-v11\.json|版本说明-v0\.11\.md|验证-v0\.11\.txt|清理记录-v0\.11\.json|regression-v11\.xml|conversions-portable-v11\.json)$' -or $oldDoc.Name -match '^(desktop-release-v10|archive-portable-v10|extra-portable-v10|native-launch-v10\.json|圆盘动态预览-v10\.gif|光圈动画记录-v10\.json|版本说明-v0\.10\.md|验证-v0\.10\.txt|清理记录-v0\.10\.json)$' -or $oldDoc.Name -match '^(archive-source-v08|archive-portable-v0[6789]|desktop-release-v0[6789]|native-launch-v0[6789]\.json|portable-(images-v06|new-v07)\.json|圆盘动态预览-v0[6789]\.gif|光圈动画记录-v0[6789]\.json|版本说明-v0\.[6789]\.md|验证-v0\.[6789]\.txt|清理记录-v0\.[6789]\.json)$')) { Remove-ManagedPath $oldDoc.FullName }
}
foreach ($fixtureName in @('动画体验.png','动画体验.gif','第一张.png','第二张.png','损坏图片.png','Word体验文件.docx','PDF体验文件.pdf','挂件体验表格.csv','K工作台体验.md','不支持的格式.bin','损坏文件.docx','无后续方向.ico','矢量体验.svg','批量第二个.csv','不同格式.jpg')) {
    Remove-ManagedPath (Join-Path $docsPath ('desktop-release-v11/' + $fixtureName))
}
foreach ($fixtureName in @('结构体验.json','结构体验.yaml','音视频体验.mp4','无音轨.mp4')) {
    Remove-ManagedPath (Join-Path $docsPath ('desktop-release-v11/' + $fixtureName))
}
Remove-ManagedPath (Join-Path $docsPath 'desktop-release-v11/archive-fixtures')

# These are generated documentation mirrors, never the app's data namespace.
foreach ($mirror in @('dist/K文件处理台/docs','dist/K文件处理台/source/docs')) {
    Remove-ManagedPath (Join-Path $taskRoot $mirror)
}
$record = @{version='1.0.0';completedAt=(Get-Date -Format 'o');removed=$script:removed;preserved=$script:preserved;retained=@('当前源码与测试','当前引擎和开发依赖','最新便携程序与压缩包','转化示意图.png','data 与最新程序 data 中的用户结果和设置','原解压项目及其数据未操作')}
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $docsPath '清理记录-v1.0.0.json') -Encoding utf8
Write-Output ('Cleanup complete: ' + $script:removed.Count + ' paths; preserved ' + $script:preserved.Count + ' data locations.')
