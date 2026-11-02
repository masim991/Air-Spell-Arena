import daily
from game import SpellGame


def test_daily_score_does_not_replace_normal_best(monkeypatch):
    game = SpellGame()
    try:
        monkeypatch.setattr("save_data.save", lambda data: None)
        monkeypatch.setattr(game, "_write_share_card", lambda *args: None)
        monkeypatch.setattr(game, "_write_highlight_clip", lambda *args: None)
        game._save["best_score"] = {"normal": 10}
        game._daily.start(daily.build("2026-09-23"))
        game.difficulty = "normal"
        game._dmg_dealt = 100
        game._finish_run(won=False)
        assert game._save["best_score"]["normal"] == 10
        assert game._save["daily"]["2026-09-23"] == game._chain_score
    finally:
        game.close()
