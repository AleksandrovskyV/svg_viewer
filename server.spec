# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=[('core', 'core')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
         #Stable
        'tkinter.test',
        'unittest', 
        'pydoc', 
        #'email', 
        #'html', 
        #'http', 
        #'xml',
        'distutils', 
        'setuptools', 
        'PIL._imagingcms',
        'PIL._tkimaging',
        'matplotlib', 
        'numpy',

         #Update
        'scipy', 
        'asyncio', 
        #'select', 
        'multiprocessing', 
        'sqlite3', 
        'dbm', 
        'gdbm', 
        #'ctypes'
        #'logging', # важен
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SVG_Viewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    icon="./assets/SVG_Viewer.ico",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
