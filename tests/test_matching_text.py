from stolen_gear_watch.core.models import WatchedItem
from stolen_gear_watch.matching.text import text_match_confidence


def make_item(**overrides):
    defaults = {"id": "test-item", "category": "camera_body", "make": "Canon", "model": "EOS R5"}
    defaults.update(overrides)
    return WatchedItem(**defaults)


def test_strong_make_model_match():
    item = make_item()
    score = text_match_confidence("Canon EOS R5 body, mint condition", "", item)
    assert score > 0.8


def test_unrelated_listing_scores_low():
    item = make_item()
    score = text_match_confidence("Nikon Z9 body only", "", item)
    assert score < 0.5


def test_keyword_boosts_score():
    text = "Canon EOS R5, has some grip tape on it"
    base = text_match_confidence(text, "", make_item())
    boosted = text_match_confidence(text, "", make_item(keywords=["grip tape"]))
    assert boosted >= base
