# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Stellaris Companion Backend.

Builds a single-file executable that includes:
- The FastAPI server (backend/electron_main.py)
- All backend modules (api, core)
- Save extractor modules (stellaris_save_extractor)
- Shared runtime package (stellaris_companion/)

Build command:
    pyinstaller --clean stellaris-backend.spec

Output:
    dist/stellaris-backend (macOS/Linux)
    dist/stellaris-backend.exe (Windows)
"""

import subprocess
import sys
from pathlib import Path

block_cipher = None

# Get the project root directory (where this spec file lives)
SPEC_ROOT = Path(SPECPATH)

# Auto-detect macOS code signing identity (Developer ID Application)
_codesign_identity = None
_entitlements_file = None
if sys.platform == 'darwin':
    _entitlements_path = SPEC_ROOT / 'electron' / 'entitlements.mac.plist'
    if _entitlements_path.exists():
        _entitlements_file = str(_entitlements_path)
    try:
        _id_output = subprocess.check_output(
            ['security', 'find-identity', '-v', '-p', 'codesigning'],
            text=True, stderr=subprocess.DEVNULL,
        )
        for line in _id_output.splitlines():
            if 'Developer ID Application' in line:
                import re
                _match = re.search(r'([0-9A-F]{40})', line)
                if _match:
                    _codesign_identity = _match.group(1)
                    break
    except Exception:
        pass
    if _codesign_identity:
        print(f'PyInstaller: signing with identity {_codesign_identity}')
    else:
        print('PyInstaller: no Developer ID found, skipping code signing')

a = Analysis(
    ['backend/electron_main.py'],
    pathex=[str(SPEC_ROOT)],
    binaries=[],
    datas=[
        # Include the stellaris_save_extractor package
        ('stellaris_save_extractor', 'stellaris_save_extractor'),
        # Include the shared runtime package (Option 1 layout)
        ('stellaris_companion', 'stellaris_companion'),
        # Prompt resources used by stellaris_companion/personality.py
        ('patches', 'patches'),
        # Include the entire backend package for imports
        ('backend', 'backend'),
    ],
    hiddenimports=[
        # Uvicorn requires these for proper startup
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        # Google GenAI SDK (google-genai package)
        'google.genai',
        'google.genai._api_client',
        'google.genai.types',
        'google.api_core',
        'google.auth',
        'google.protobuf',
        # FastAPI and dependencies
        'fastapi',
        'starlette',
        'starlette.routing',
        'starlette.middleware',
        'starlette.middleware.cors',
        'pydantic',
        'pydantic_core',
        'anyio',
        'anyio._backends._asyncio',
        # Watchdog for save file monitoring
        'watchdog.observers',
        'watchdog.events',
        # Performance: orjson for ~3x faster JSON serialization
        'orjson',
        # Standard library modules that may be missed
        'sqlite3',
        'json',
        'hashlib',
        'zipfile',
        'email.mime.text',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude discord.py - not needed for Electron backend
        'discord',
        # Exclude test modules
        'pytest',
        'unittest',
        # Exclude development tools
        'black',
        'mypy',
        'pylint',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='stellaris-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window - runs as background service
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    exclude_binaries=True,
    codesign_identity=_codesign_identity,
    entitlements_file=_entitlements_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='stellaris-backend',
)
