# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['yolo8.py'],
    pathex=['C:\\Users\\maisfluxo\\Desktop\\projeto_veiculos_mais_fluxo'],
    binaries=[],
    datas=[
        # Ajuste os caminhos para apontar para o local correto dos arquivos dentro do site-packages global
        ('C:\\Users\\maisfluxo\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages\\ultralytics\\cfg\\default.yaml', 'ultralytics/cfg'),
        ('C:\\Users\\maisfluxo\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages\\ultralytics\\cfg\\trackers\\botsort.yaml', 'ultralytics/cfg/trackers')
    ],
    hiddenimports=['torch', 'torchvision', 'numpy', 'cv2', 'keyboard'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='yolo8',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='yolo8',
)
