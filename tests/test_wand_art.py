"""The spell originates at the visible wand gem as the player moves."""
import pygame

from fp_renderer import FPRenderer


def test_spell_origin_tracks_rendered_wand_gem():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    font = pygame.font.Font(None, 24)
    renderer = FPRenderer(screen, font, font)
    assert renderer._wand_art is not None
    for tick, offset in ((0, 0), (35, 0.6), (70, -0.6)):
        renderer._tick = tick
        screen.fill((0, 0, 0))
        renderer._draw_wand(offset)
        red, green, blue, _ = screen.get_at(renderer.wand_tip(offset))
        assert min(red, green, blue) > 120  # the pale gem, not background


def test_art_load_failure_uses_fallback(monkeypatch):
    def unreadable(_path):
        raise PermissionError("image unavailable")

    monkeypatch.setattr(pygame.image, "load", unreadable)
    assert FPRenderer._load_art("player_wand.png", (310, 310)) is None
