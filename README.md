# Air Spell Arena

웹캠 모션 캡처로 마법을 시전해 보스와 싸우는 파이썬 게임.
MediaPipe(손/얼굴 추적) + OpenCV(카메라) + Pygame(게임 렌더)로 동작합니다.

## 설치

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

- **Python 3.12 필요** (MediaPipe 0.10.x 는 3.9~3.12 지원, 3.13 미지원).
- GPU 불필요. CPU 추론으로 동작합니다.

## 실행

```bash
python main.py
```

- Pygame 창(게임)과 OpenCV `Tracking` 창(웹캠 미러)이 함께 뜹니다.
- 종료: 게임 창에서 `ESC`, 또는 `Tracking` 창에서 `q`.
- `main.py` 상단 옵션:
  - `SHOW_DEBUG_WINDOWS` — 웹캠 디버그 창 표시 여부.
  - `CAMERA_INDEX` — 웹캠이 여러 대일 때 조정.
  - `USE_HAND_TRACKING` — `True`: MediaPipe 손가락 추적, `False`: HSV 색상 마커 추적(`air_canvas.py`).

## 조작

### 1. 포즈 주문 (손 모양을 ~10프레임 유지)
| 포즈 | 주문 |
|------|------|
| 손바닥 펼치기(다섯 손가락) | FIRE |
| 주먹 | WATER |
| 엄지만 세우기 | EARTH |
| 검지만 펴기 | WIND |

### 2. 궤적 주문 (검지 끝으로 허공에 그리기)
| 궤적 | 주문 |
|------|------|
| 왼쪽으로 수평 이동 | LIGHT (실드) |
| 오른쪽으로 수평 이동 | DARK |
| 원 | CIRCLE → 실드 |
| 지그재그 | ZIGZAG → 라이트닝 (쿨다운 4초) |

두 개의 기본 주문을 1.2초 안에 연속 시전하면 콤보로 합쳐집니다
(`spell_combo.py`: FIRE+WATER→STEAM 등).

### 3. 머리로 회피
얼굴을 **왼쪽/오른쪽으로 기울이면** 플레이어가 그 방향으로 이동해 보스 투사체를 피합니다.
정면을 보면 서서히 중앙으로 복귀합니다.

### 4. 키보드 폴백 (데모·테스트·접근성)
카메라 없이도 플레이할 수 있습니다. 게임 진행(playing) 중:
| 키 | 동작 |
|----|------|
| `1`~`7` | FIRE / WATER / WIND / EARTH / DARK / LIGHT / LIGHTNING |
| `←` `→` | 좌/우 회피 (누르는 동안 이동, 카메라보다 우선) |
| `ESC` | 일시정지 |

보스는 HP에 따라 3페이즈로 강화되며(원소 FIRE→WATER→DARK, 공격 가속),
시전 0.5초 전 붉은 경고 링이 표시됩니다. 주문 상성이 맞으면 1.5×, 불리하면 0.6× 피해.

## 카메라 요구사항
- 720p 웹캠 권장, 30 FPS 이상.
- 상반신과 한쪽 손이 프레임에 들어오는 거리(약 0.6~1.2 m).
- 균일한 조명(역광 피하기). 손과 배경 대비가 낮으면 인식률이 떨어집니다.

## 개발 / 테스트

```bash
pip install -r requirements-dev.txt
ruff check .          # 린트 (E9 + pyflakes)
pytest                # 헤드리스 테스트 (SDL dummy 자동 설정)
```

CI(`.github/workflows/ci.yml`)가 push/PR마다 ruff + pytest를 실행합니다.

## 패키징

```bash
pip install pyinstaller
pyinstaller airspellarena.spec     # → dist/AirSpellArena(.exe), sounds/ 동봉
```

## 모듈 구조
| 파일 | 역할 |
|------|------|
| `main.py` | 메인 루프 — 비전/제스처/게임 조율 |
| `vision_loop.py` | MediaPipe Hands + FaceMesh 프레임 처리 |
| `head_tracker.py` | 얼굴 방향(LEFT/RIGHT/CENTER) 판정 |
| `gesture.py` | 포즈 / 궤적 → 주문 분류 |
| `trajectory.py` | 검지 끝 좌표 스트림을 스트로크로 분할 |
| `spell_combo.py` | 기본 주문 시간축 콤보 규칙 |
| `game.py` | 게임 상태, 주문 효과, 보스 AI |
| `fp_renderer.py` | 1인칭 시점 렌더링 |
| `audio_manager.py` | BGM / 주문별 SFX 슬롯 관리 |
| `air_canvas.py` | HSV 마커 추적 대체 입력 경로 |
