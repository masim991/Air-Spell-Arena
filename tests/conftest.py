import os
import sys

# 헤드리스 환경(CI)에서도 pygame 초기화가 가능하도록 더미 드라이버 사용
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
