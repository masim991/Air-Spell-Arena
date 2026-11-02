import pygame

from game import SpellGame


def test_pause_uses_current_volume_and_excludes_pause_time(monkeypatch):
    game = SpellGame()
    try:
        game._state = "playing"
        game._run_start_ms = 1000
        monkeypatch.setattr(game._audio, "get_volume", lambda slot: 13 if slot == "bgm" else 27)
        monkeypatch.setattr(pygame.time, "get_ticks", lambda: 2000)
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        game.run_one_frame(None)
        assert game._state == "pause"
        assert game._pause_vols == {"bgm": 13, "sfx": 27}
        monkeypatch.setattr(pygame.time, "get_ticks", lambda: 7000)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        game.run_one_frame(None)
        assert game._run_start_ms == 6000
    finally:
        game.close()
