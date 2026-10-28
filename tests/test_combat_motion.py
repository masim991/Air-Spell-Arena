"""Combat events must drive the poses shown to the player."""
import pygame

from fp_renderer import FPRenderer
from game import SpellGame


def make_renderer():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    font = pygame.font.Font(None, 24)
    return FPRenderer(screen, font, font)


def test_boss_atlases_and_combat_state_selection():
    renderer = make_renderer()
    for frames in renderer._boss_motion.values():
        assert len(frames) == 36
        assert pygame.image.tobytes(frames[0], "RGBA") != pygame.image.tobytes(frames[29], "RGBA")
        for frame in frames:
            bounds = frame.get_bounding_rect(min_alpha=1)
            assert bounds.left > 0 and bounds.top > 0
            assert bounds.right < frame.get_width() and bounds.bottom < frame.get_height()
    assert renderer._boss_frame_index([{"type": "telegraph", "elapsed": 50, "dur": 500}]) == 12
    assert renderer._boss_frame_index([{"type": "telegraph", "elapsed": 350, "dur": 500}]) == 17
    assert renderer._boss_frame_index([{"type": "proj", "origin": "boss", "elapsed": 10}]) == 20
    assert renderer._boss_frame_index([{"type": "boss_guard", "elapsed": 150, "dur": 420}]) == 28
    assert renderer._boss_frame_index([{"type": "boss_guard", "elapsed": 100, "dur": 420},
                                       {"type": "proj", "origin": "boss", "elapsed": 10}]) == 20


def test_attack_styles_move_wand_differently():
    renderer = make_renderer()
    poses = set()
    for style in ("fire", "water", "wind", "earth", "dark", "light", "lightning"):
        renderer._update_wand_pose([{"type": "player_motion", "style": style,
                                    "elapsed": 225, "dur": 450}], 0, 220)
        poses.add(renderer._wand_pose)
    assert len(poses) == 7


def test_boss_projectile_leaves_animated_hand(monkeypatch):
    renderer = make_renderer()
    shots = []
    monkeypatch.setattr(renderer, "_draw_proj_styled", lambda *args: shots.append(args))
    projectile = {"type": "proj", "origin": "boss", "elapsed": 0, "dur": 1000,
                  "color": (255, 80, 40), "hand_side": -1, "origin_visual_offset": 0}
    renderer._draw_boss(1, [projectile], 0)
    expected = renderer._boss_hand_deltas[-1]
    renderer._draw_effects([projectile])
    assert shots[0][0:2] == (640 + expected[0], 332 + expected[1])
    assert projectile["render_hand_delta"] == expected


def test_boss_elements_and_spread_use_distinct_effects_and_hands():
    game = SpellGame()
    try:
        for element in ("FIRE", "WATER", "WIND", "EARTH", "DARK", "LIGHT"):
            game.boss_element = element
            game._spawn_boss_projectile(10, end=(game.player_pos[0] - 100, game.player_pos[1]))
            shot = game._effects[-1]
            assert shot["style"] == element.lower()
            assert shot["hand_side"] == -1
        game._spawn_boss_projectile(10, end=(game.player_pos[0] + 100, game.player_pos[1]))
        assert game._effects[-1]["hand_side"] == 1
    finally:
        game.close()


def test_wand_cast_and_shield_pose_follow_visible_gem():
    renderer = make_renderer()
    for effects, shield in (([{"type": "player_motion", "elapsed": 225, "dur": 450}], 0),
                            ([], 2000)):
        renderer._update_wand_pose(effects, shield, 220)
        assert renderer._wand_pose != (0, 0, 0)
        renderer.screen.fill((0, 0, 0))
        renderer._draw_wand(.3)
        r, g, b, _ = renderer.screen.get_at(renderer.wand_tip(.3))
        assert min(r, g, b) > 100


def test_boss_dodge_triggers_guard_motion(monkeypatch):
    game = SpellGame()
    try:
        game._boss_dodge_prob = 1.0
        monkeypatch.setattr("game.random.random", lambda: 0.0)
        old_position = game.boss_pos
        game._spawn_player_projectile("FIRE", (255, 80, 40), 10, 1000, "fire")
        game._update_effects(700)
        assert game.boss_pos != old_position
        assert any(e["type"] == "boss_guard" for e in game._effects)
        game._update_effects(421)
        assert not any(e["type"] == "boss_guard" for e in game._effects)
    finally:
        game.close()


def test_projectile_keeps_its_aim_when_boss_dodges(monkeypatch):
    renderer = make_renderer()
    shots = []
    monkeypatch.setattr(renderer, "_draw_proj_styled", lambda *args: shots.append(args))
    projectile = {"type": "proj", "origin": "player", "elapsed": 500, "dur": 1000,
                  "color": (255, 80, 40), "target_visual_offset": 0}
    renderer._draw_effects([projectile], boss_offset_x=-90)
    assert shots[0][-2:] == (640, 332)  # projectile aims at the pre-dodge position
