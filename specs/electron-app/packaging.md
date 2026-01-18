# Electron App - Packaging Specification

## Overview

The app bundles:
1. **Electron shell** - JavaScript/HTML/CSS
2. **Python backend** - PyInstaller single-file executable
3. **Assets** - Icons, tray images

## PyInstaller Configuration

### Spec File: `stellaris-backend.spec`

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['backend/electron_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('stellaris_save_extractor', 'stellaris_save_extractor'),
        ('personality.py', '.'),
        ('save_extractor.py', '.'),
        ('save_loader.py', '.'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.lifespan.on',
        'google.genai',
        'google.ai.generativelanguage',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='stellaris-backend',
    debug=False,
    strip=False,
    upx=True,
    console=False,  # No console window
)
```

### Build Commands

```bash
# macOS
pyinstaller --clean stellaris-backend.spec
mv dist/stellaris-backend dist-python/stellaris-backend

# Windows
pyinstaller --clean stellaris-backend.spec
move dist\stellaris-backend.exe dist-python\stellaris-backend.exe

# Linux
pyinstaller --clean stellaris-backend.spec
mv dist/stellaris-backend dist-python/stellaris-backend
```

## Electron Builder Configuration

### electron-builder.yml

```yaml
appId: com.stellaris.companion
productName: Stellaris Companion

directories:
  output: dist

files:
  - main.js
  - preload.js
  - renderer/dist/**/*

extraResources:
  - from: ../dist-python
    to: python-backend
    filter:
      - "**/*"

mac:
  category: public.app-category.games
  icon: assets/icon.icns
  target:
    - target: dmg
      arch: [x64, arm64]
    - target: zip
      arch: [x64, arm64]
  hardenedRuntime: true
  gatekeeperAssess: false
  entitlements: entitlements.mac.plist
  entitlementsInherit: entitlements.mac.plist

win:
  icon: assets/icon.ico
  target:
    - target: nsis
      arch: [x64]
  signAndEditExecutable: false  # Enable when code signing

linux:
  icon: assets/icon.png
  target:
    - target: AppImage
      arch: [x64]
  category: Game

nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
  createStartMenuShortcut: true

publish:
  provider: github
  owner: YOUR_GITHUB_USERNAME
  repo: stellaris-companion
  releaseType: release
```

### Entitlements (macOS): `entitlements.mac.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
    <key>com.apple.security.cs.allow-dyld-environment-variables</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
</dict>
</plist>
```

## Build Scripts

### scripts/build-python.sh

```bash
#!/bin/bash
set -e

echo "Building Python backend..."

# Create output directory
mkdir -p dist-python

# Build with PyInstaller
pyinstaller --clean stellaris-backend.spec

# Move to expected location
if [[ "$OSTYPE" == "darwin"* ]]; then
    mv dist/stellaris-backend dist-python/stellaris-backend
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    mv dist/stellaris-backend.exe dist-python/stellaris-backend.exe
else
    mv dist/stellaris-backend dist-python/stellaris-backend
fi

echo "Python backend built successfully"
```

### scripts/build-electron.sh

```bash
#!/bin/bash
set -e

echo "Building Electron app..."

cd electron

# Install dependencies
npm ci

# Build React app
cd renderer
npm run build
cd ..

# Build Electron
npm run build

echo "Electron app built successfully"
```

### scripts/build-all.sh

```bash
#!/bin/bash
set -e

echo "=== Full Build ==="

# Build Python first
./scripts/build-python.sh

# Then Electron (includes Python in extraResources)
./scripts/build-electron.sh

echo "=== Build Complete ==="
echo "Output: electron/dist/"
```

## Path Resolution in Packaged App

### main.js - getPythonPath()

```javascript
function getPythonPath() {
  if (app.isPackaged) {
    const platform = process.platform;
    const ext = platform === 'win32' ? '.exe' : '';
    return path.join(
      process.resourcesPath,
      'python-backend',
      `stellaris-backend${ext}`
    );
  } else {
    // Development: use system Python
    return 'python';
  }
}

function getPythonArgs() {
  if (app.isPackaged) {
    return [];  // PyInstaller executable, no args needed
  } else {
    return ['backend/electron_main.py'];
  }
}

function getPythonCwd() {
  if (app.isPackaged) {
    return process.resourcesPath;
  } else {
    return path.join(__dirname, '..');
  }
}
```

## Database Path

Always use `app.getPath('userData')` for writable data:

```javascript
const dbPath = path.join(app.getPath('userData'), 'stellaris_history.db');
```

This resolves to:
- macOS: `~/Library/Application Support/Stellaris Companion/stellaris_history.db`
- Windows: `%APPDATA%\Stellaris Companion\stellaris_history.db`
- Linux: `~/.config/Stellaris Companion/stellaris_history.db`

## GitHub Actions CI/CD

### .github/workflows/release.yml

```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-python:
    strategy:
      matrix:
        include:
          - os: macos-latest
            arch: x64
          - os: macos-latest
            arch: arm64
          - os: windows-latest
            arch: x64
          - os: ubuntu-latest
            arch: x64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller

      - name: Build Python backend
        run: pyinstaller --clean stellaris-backend.spec

      - name: Upload Python artifact
        uses: actions/upload-artifact@v4
        with:
          name: python-backend-${{ matrix.os }}-${{ matrix.arch }}
          path: dist/stellaris-backend*

  build-electron:
    needs: build-python
    strategy:
      matrix:
        include:
          - os: macos-latest
            arch: x64
          - os: macos-latest
            arch: arm64
          - os: windows-latest
            arch: x64
          - os: ubuntu-latest
            arch: x64
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Download Python backend
        uses: actions/download-artifact@v4
        with:
          name: python-backend-${{ matrix.os }}-${{ matrix.arch }}
          path: dist-python/

      - name: Make Python executable
        if: runner.os != 'Windows'
        run: chmod +x dist-python/stellaris-backend

      - name: Install Electron deps
        working-directory: electron
        run: npm ci

      - name: Build React app
        working-directory: electron/renderer
        run: npm run build

      - name: Build Electron app
        working-directory: electron
        run: npm run build
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Upload to GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: |
            electron/dist/*.dmg
            electron/dist/*.zip
            electron/dist/*.exe
            electron/dist/*.AppImage
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Version Management

Use same version in:
1. `electron/package.json` - "version": "1.0.0"
2. Git tag - `v1.0.0`
3. Release notes

Bump version before tagging:
```bash
cd electron
npm version patch  # or minor, major
git push && git push --tags
```

## Future: Code Signing

### macOS

1. Get Apple Developer account
2. Create Developer ID Application certificate
3. Add to electron-builder.yml:
```yaml
mac:
  identity: "Developer ID Application: Your Name (TEAM_ID)"
```
4. Notarize after build:
```bash
xcrun notarytool submit app.dmg --apple-id EMAIL --team-id TEAM_ID --password @keychain:AC_PASSWORD
```

### Windows

1. Get EV code signing certificate
2. Add to electron-builder.yml:
```yaml
win:
  certificateFile: path/to/cert.pfx
  certificatePassword: ${WIN_CERT_PASSWORD}
```
