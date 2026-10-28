# PyInstaller 스펙 — 원파일 빌드. 음원 권리 확인 전에는 무음 빌드.
#   pip install pyinstaller
#   pyinstaller airspellarena.spec
# 결과물: dist/AirSpellArena(.exe)

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# MediaPipe 모델(.tflite/.binarypb) · Pygame 데이터 동봉
# sounds/custom 은 배포권 근거가 없어 번들하지 않는다(사용자가 자기 폴더에 직접 넣는 용도).
# 최상위 sounds/ 파일도 권리 확인 전에는 기본적으로 번들하지 않는다(릴리스 게이트).
# 권리를 확인한 음원으로 빌드할 때만 AIRSPELL_AUDIO_CLEARED=1 을 설정한다 — README "오디오 권리" 참고.
import os
datas = []
if os.environ.get("AIRSPELL_AUDIO_CLEARED") == "1":
    datas += [
        (os.path.join("sounds", f), "sounds")
        for f in sorted(os.listdir("sounds"))
        if os.path.isfile(os.path.join("sounds", f)) and f.lower() != "readme.txt"
    ]
else:
    print("[spec] audio rights NOT cleared: sounds/ is not bundled (silent build). "
          "Set AIRSPELL_AUDIO_CLEARED=1 only after verifying rights.")
datas += [("audio_config.json", ".")]
datas += [("assets", "assets")]
datas += collect_data_files("mediapipe")
hiddenimports = [
    "mediapipe.python.solutions.hands",
    "mediapipe.python.solutions.drawing_utils",
    "mediapipe.python.solutions.drawing_styles",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # MediaPipe imports drawing_utils during startup, which requires matplotlib.
    excludes=["tkinter", "pytest"],
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
