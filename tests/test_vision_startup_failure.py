from unittest.mock import MagicMock

import pytest

import main
import vision_loop


@pytest.mark.parametrize('stage', ['hands', 'head'])
def test_pipeline_releases_created_resources_when_initialization_fails(monkeypatch, stage):
    cap = MagicMock()
    hands = MagicMock()
    monkeypatch.setattr(vision_loop.cv2, 'VideoCapture', lambda index: cap)
    if stage == 'hands':
        monkeypatch.setattr(vision_loop.mp_hands, 'Hands', MagicMock(side_effect=RuntimeError('hands failed')))
    else:
        monkeypatch.setattr(vision_loop.mp_hands, 'Hands', MagicMock(return_value=hands))
        monkeypatch.setattr(vision_loop, 'HeadTracker', MagicMock(side_effect=RuntimeError('head failed')))
    with pytest.raises(RuntimeError):
        vision_loop.VisionPipeline(99)
    cap.release.assert_called_once()
    if stage == 'head':
        hands.close.assert_called_once()


def test_pipeline_initialization_error_falls_back_to_keyboard(monkeypatch):
    game = MagicMock()
    monkeypatch.setattr(main, 'VisionPipeline', MagicMock(side_effect=RuntimeError('initialization failed')))
    assert main._open_pipeline(game) is None
    game.set_camera_active.assert_called_once_with(False)
    game.notify_camera_error.assert_called_once()


def test_worker_start_error_closes_pipeline_and_falls_back(monkeypatch):
    game = MagicMock()
    pipeline = MagicMock()
    pipeline.start.side_effect = RuntimeError('thread start failed')
    monkeypatch.setattr(main, 'VisionPipeline', MagicMock(return_value=pipeline))
    assert main._open_pipeline(game) is None
    pipeline.close.assert_called_once()
    game.set_camera_active.assert_called_once_with(False)
    game.notify_camera_error.assert_called_once()
