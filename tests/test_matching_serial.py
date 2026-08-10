from stolen_gear_watch.matching.serial import serial_match_confidence


def test_exact_token_match():
    assert serial_match_confidence("Canon EOS R5, serial 123456789012", "123456789012") == 1.0


def test_dashes_and_case_are_normalized():
    assert serial_match_confidence("SN: 1234-5678-9012", "123456789012") > 0.0


def test_no_match_returns_zero():
    assert serial_match_confidence("Canon EOS R6 for sale, great condition", "123456789012") == 0.0


def test_short_serial_is_refused_to_avoid_false_positives():
    # A 3-character "serial" could coincidentally appear almost anywhere -
    # matching it would create noisy false alerts.
    assert serial_match_confidence("lot 123 of camera gear", "123") == 0.0
