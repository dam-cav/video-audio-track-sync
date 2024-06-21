# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['video_audio_track_sync_scenes_dynamic_speed.py'],
    pathex=['..'],
    binaries=[],
    datas=[('../common/', 'common')],
    hiddenimports=['common.utils'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='video_audio_track_sync_scenes_dynamic_speed',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='video_audio_track_sync_scenes_dynamic_speed',
)
