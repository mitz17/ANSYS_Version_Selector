# Build all version selector tools with PyInstaller
param([switch]$Clean)

function Ensure-PyInstaller {
    if (-not (py -3 -m PyInstaller --version 2>$null)) {
        py -3 -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
        py -3 -m pip install pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "pyinstaller install failed" }
    }
}

try {
    Ensure-PyInstaller
    $cleanArg = if ($Clean) { "--clean" } else { "" }

    $targets = @(
        @{ Name='FluentVersionSelector'; Target='./Fluent_Launcher.py'; Icon='./Fluent.ico' },
        @{ Name='SpaceClaimVersionSelector'; Target='./SpaceClaim_Launcher.py'; Icon='./spaceclaim.ico' },
        @{ Name='WorkbenchVersionSelector'; Target='./Workbench_Launcher.py'; Icon='./workbench.ico' }
    )

    foreach ($t in $targets) {
        Write-Host "Building $($t.Name) ..."
        $args = @("--noconfirm")
        if ($cleanArg) { $args += $cleanArg }
        $args += @("--windowed", "--onefile", "--noupx", "--name", $t.Name)
        if ($t.Icon -and (Test-Path $t.Icon)) {
            $args += @("--icon", $t.Icon)
        }
        $args += $t.Target
        & py -3 -m PyInstaller @args
        if ($LASTEXITCODE -ne 0) { throw "build failed for $($t.Name)" }
    }
    Write-Host "All builds finished. See dist\\*.exe"
} catch {
    Write-Error $_
    exit 1
}
