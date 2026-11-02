import pygame

from game import SpellGame


def test_keyboard_fire_casts_without_camera():
    game = SpellGame()
    try:
        game._state = "playing"
        game.set_camera_active(False)
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
        assert game.run_one_frame(None)
        assert game._spells_cast == 1
    finally:
        game.close()
