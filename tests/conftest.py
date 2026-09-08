"""pytest 공통 설정 — Pygame/OpenCV 를 헤드리스로 강제."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# GUI/오디오 장치 없이 동작하도록 (CI 포함)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "2")
