# PyInstaller 스펙 — 원파일 빌드 + sounds/ 번들.
#   pip install pyinstaller
#   pyinstaller airspellarena.spec
# 결과물: dist/AirSpellArena(.exe)

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# MediaPipe 모델(.tflite/.binarypb) · Pygame 데이터 동봉
datas = [("sounds", "sounds")]
datas += collect_data_files("mediapipe")
hiddenimports = collect_submodules("mediapipe")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
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
    name="AirSpellArena",
    debug=False,
    strip=False,
    upx=True,
    console=False,          # 창모드(콘솔 숨김); 디버깅 시 True
    disable_windowed_traceback=False,
)
