"""PaddleOCR Engine Provider Implementation."""

from __future__ import annotations

import logging
import time
import numpy as np

from .base import BaseOcrEngine, OcrResult
from .. import ocr_service

logger = logging.getLogger(__name__)


class PaddleOcrEngine(BaseOcrEngine):
    """PaddleOCR provider engine implementation."""

    def run_ocr(
        self,
        image: np.ndarray,
        scale: float = 1.0,
        lang: str | None = None,
    ) -> OcrResult:
        res = ocr_service._run_paddle_ocr(image, scale=scale, lang=lang)
        return OcrResult(lines=res.lines, elapsed_ms=res.elapsed_ms)
