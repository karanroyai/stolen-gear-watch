from stolen_gear_watch.core.config import OcrSettings
from stolen_gear_watch.matching.ocr import get_ocr


def test_get_ocr_none_by_default():
    assert get_ocr(OcrSettings()) is None


def test_get_ocr_none_for_unknown_backend():
    assert get_ocr(OcrSettings(backend="something-unrecognized")) is None
