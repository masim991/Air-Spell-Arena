"""Regression checks for recorder data at game and privacy boundaries."""

import pygame

import share_card
from game import SpellGame


def test_disabling_face_in_media_discards_existing_clip_frames():
    game = SpellGame()
    try:
        game._state = "menu"
        game._save["face_in_media"] = True
        game._recorder._frames.append(b"previously unmasked frame")
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f))

        game.run_one_frame(None)

        assert game._save["face_in_media"] is False
        assert len(game._recorder) == 0
    finally:
        game.close()


def test_starting_new_run_discards_previous_run_frames():
    game = SpellGame()
    try:
        game._recorder._frames.append(b"previous run frame")

        game._start_new_run()

        assert len(game._recorder) == 0
    finally:
        game.close()


def test_disabled_orb_is_not_included_in_share_card(monkeypatch):
    game = SpellGame()
    try:
        game._state = "playing"
        game._save["face_in_media"] = True
        game._orb._surface = pygame.Surface((8, 8))
        game._orb.set_enabled(True)
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v))
        game.run_one_frame(None)
        assert not game._orb.enabled
        assert game._orb.portrait() is not None  # previously captured frame

        captured = []
        monkeypatch.setattr(share_card, "build_card", lambda **kwargs: captured.append(kwargs) or None)
        monkeypatch.setattr(share_card, "save_card", lambda card: "")
        game._write_share_card(True, 1, False)
        assert captured[0]["portrait"] is None

        game._orb.set_enabled(True)
        game._write_share_card(True, 1, False)
        assert captured[1]["portrait"] is game._orb.portrait()

        game._save["face_in_media"] = False
        game._write_share_card(True, 1, False)
        assert captured[2]["portrait"] is None
    finally:
        game.close()
