# PyInstaller spec for NovaBlock
# Build: pyinstaller novablock.spec --clean

from PyInstaller.utils.hooks.tcl_tk import tcltk_info

# A successful link alone is insufficient: some Windows Python runtimes expose
# Tcl/Tk resources only through Tcl's virtual filesystem, which the hook
# cannot copy. Fail the build instead of shipping an exe that won't open.
gui_files = {destination.replace("\\", "/") for destination, _, _ in tcltk_info.data_files}
missing_gui_files = {"_tcl_data/init.tcl", "_tk_data/tk.tcl"} - gui_files
if missing_gui_files:
    raise SystemExit(
        "Cannot package Tcl/Tk resources: " + ", ".join(sorted(missing_gui_files))
        + ". Use the Windows Python 3.12 release runtime with Tcl/Tk installed."
    )

block_cipher = None

a = Analysis(
    ['__main__.py'],
    pathex=['.'],
    binaries=[('build/relay.exe', '.')],
    datas=[],
    hiddenimports=[
        'pystray._win32',
        'PIL._tkinter_finder',
        'win32com',
        'win32com.client',
        'win32security',
        'pywinauto',
        'pywinauto.controls.uiawrapper',
        'comtypes',
        'comtypes.client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'IPython', 'jupyter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NovaBlock',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    manifest='app_manifest.xml',
    icon='assets/icon.ico' if __import__('os').path.exists('assets/icon.ico') else None,
)
