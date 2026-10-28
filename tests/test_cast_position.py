"""Spells start at the current first-person wand position."""

import pytest

from game import SCREEN_W, SpellGame


@pytest.mark.parametrize("offset", [-0.6, 0.0, 0.6])
def test_spell_particles_start_at_moved_wand_tip(monkeypatch, offset):
    game = SpellGame()
    try:
        game._player_fx = SCREEN_W / 2 * (1 + offset)
        expected = game._fp.wand_tip(offset)
        particles = []
        monkeypatch.setattr(game._fp, "add_particles", lambda x, y, *args: particles.append((x, y)))

        assert game.apply_spell("FIRE").applied
        assert particles[0] == expected
    finally:
        game.close()
