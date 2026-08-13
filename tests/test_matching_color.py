from stolen_gear_watch.matching.color import mentions_conflicting_color


def test_conflicting_color_is_detected():
    assert mentions_conflicting_color("Fujifilm X100VI Schwarz, neuwertig", "silver") is True


def test_matching_color_is_not_conflicting():
    assert mentions_conflicting_color("Fujifilm X100VI Silber, neuwertig", "silver") is False


def test_no_color_mentioned_is_not_conflicting():
    # Absence of color info is not evidence of the wrong color.
    assert mentions_conflicting_color("Fujifilm X100VI, top Zustand", "silver") is False


def test_both_colors_mentioned_is_not_conflicting():
    # e.g. "available in black or silver" - legitimately ambiguous, don't filter.
    assert mentions_conflicting_color("X100VI in schwarz oder silber verfügbar", "silver") is False


def test_unrecognized_item_color_never_filters():
    assert mentions_conflicting_color("Fujifilm X100VI Schwarz", "burgundy") is False
