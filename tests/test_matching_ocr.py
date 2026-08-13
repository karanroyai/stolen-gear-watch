from stolen_gear_watch.core.config import ReverseImageSettings
from stolen_gear_watch.matching.ocr import get_ocr


def test_get_ocr_none_for_manual_backend():
    assert get_ocr(ReverseImageSettings(backend="manual")) is None


def test_get_ocr_none_for_tineye_backend():
    # No Vision-equivalent OCR feature for TinEye - should be skipped, not
    # raise, so a run isn't broken by picking a backend without OCR support.
    assert get_ocr(ReverseImageSettings(backend="tineye")) is None
