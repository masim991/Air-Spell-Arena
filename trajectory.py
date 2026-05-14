from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

Point = Tuple[int, int]
Trajectory = List[Point]


@dataclass(frozen=True)
class TrajectoryConfig:
    """궤적(스트로크) 종료/보관 관련 설정."""

    disappear_frames_to_close: int = 2
    max_trajectories: int = 10
    min_points_to_keep: int = 4


class TrajectoryBuffer:
    """프레임 단위로 들어오는 중심점(center) 스트림을 스트로크(궤적) 단위로 묶어 저장합니다."""

    def __init__(self, config: TrajectoryConfig | None = None) -> None:
        self._cfg = config or TrajectoryConfig()
        self._active: Trajectory = []
        self._recent: Deque[Trajectory] = deque(maxlen=self._cfg.max_trajectories)

        self._absent_frames: int = 0
        self._was_present: bool = False

        self._just_closed: bool = False
        self._last_closed: Optional[Trajectory] = None

    def update(self, center: Optional[Point]) -> None:
        """현재 프레임의 중심점을 반영하여 궤적을 갱신합니다.

        - center가 None이 아니면: active trajectory에 추가
        - center가 None이면: 결손 프레임 누적 → 설정 프레임 이상이면 trajectory 종료
        """
        self._just_closed = False
        self._last_closed = None

        if center is not None:
            if not self._was_present:
                self._active = []
            self._active.append(center)
            self._absent_frames = 0
            self._was_present = True
            return

        # center is None
        if not self._was_present:
            return

        self._absent_frames += 1
        if self._absent_frames < self._cfg.disappear_frames_to_close:
            return

        # close
        self._close_active()

    def _close_active(self) -> None:
        traj = list(self._active)
        self._active = []
        self._absent_frames = 0
        self._was_present = False

        if len(traj) < self._cfg.min_points_to_keep:
            return

        self._recent.append(traj)
        self._just_closed = True
        self._last_closed = traj

    def get_recent_trajectories(self) -> List[Trajectory]:
        """최근 완료된 궤적들을 오래된 순서 → 최신 순서로 반환합니다."""
        return list(self._recent)

    def poll_last_closed(self) -> Optional[Trajectory]:
        """직전에 '완료'된 궤적이 있으면 1회성으로 반환하고, 없으면 None.

        같은 궤적을 중복 반환하지 않도록 poll 형태로 제공합니다.
        """
        if not self._just_closed:
            return None
        self._just_closed = False
        return self._last_closed
