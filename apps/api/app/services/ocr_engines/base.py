"""Abstract base class for OCR Engine providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np

from ...schemas.core import OcrLine


class OcrResult:
    def __init__(self, lines: list[OcrLine], elapsed_ms: int):
        self.lines = lines
        self.elapsed_ms = elapsed_ms


class BaseOcrEngine(ABC):
    """Abstract interface that all OCR providers (PaddleOCR, NVIDIA Eagle VLM, etc.) implement."""

    @abstractmethod
    def run_ocr(
        self,
        image: np.ndarray,
        scale: float = 1.0,
        lang: str | None = None,
    ) -> OcrResult:
        """Process an image array and return extracted lines with bounding boxes."""
        pass
