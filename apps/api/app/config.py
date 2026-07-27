"""Central configuration, loaded from environment with sane defaults.

Every tunable that affects OCR quality lives here so it can be adjusted
without touching code -- see `.env.example` for the documented set.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = .../apps/api/app/config.py -> up 4 levels
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "apps" / "api" / ".env"),
        env_prefix="OCR_",
        extra="ignore",
    )

    # ---------------------------------------------------------------- paths
    data_dir: Path = Field(default=REPO_ROOT / "data")
    """Root for the SQLite db, uploaded PDFs and rendered page images."""

    # ------------------------------------------------------------- database
    database_url: str = ""
    """Overridable; defaults to sqlite in `data_dir` (resolved in `db.py`)."""

    # ---------------------------------------------------------- pdf / images
    render_dpi: int = 300
    """DPI used by PyMuPDF when rasterising a PDF page.

    NOTE: for already-rasterised PDFs (a single full-page image, as in the
    electoral-roll corpus) this cannot recover detail that isn't in the file.
    `upscale_factor` below is what actually helps those.
    """

    max_page_pixels: int = 40_000_000
    """Guard against decompression bombs / absurd page sizes."""

    # ------------------------------------------------------- preprocessing
    upscale_factor: float = 2.0
    """Bicubic upscale applied before OCR. Source scans are ~144 DPI; small
    Tamil glyphs recognise far better after upscaling."""

    denoise_enabled: bool = True
    denoise_strength: int = 7
    """`h` parameter for cv2.fastNlMeansDenoising. Applied BEFORE CLAHE so
    contrast enhancement doesn't amplify paper grain."""

    clahe_enabled: bool = True
    clahe_clip_limit: float = 2.0
    clahe_tile_grid: int = 8

    unsharp_enabled: bool = True
    unsharp_amount: float = 0.6
    unsharp_radius: int = 3
    """Mild unsharp mask after upscaling to crisp up Tamil character edges."""

    deskew_enabled: bool = True
    deskew_max_angle: float = 5.0
    """Only correct small skews; a larger estimate usually means the estimator
    latched onto page furniture rather than text baselines."""

    # ------------------------------------------------------------ paddleocr
    ocr_lang: str = "ta"
    """Default recognition language. `ta` = Tamil (PP-OCRv5 multilingual)."""

    ocr_version: str = "PP-OCRv5"
    """PP-OCRv5 is the version with documented Tamil support. v6 is newer but
    does not publish a Tamil recognition model at time of writing."""

    ocr_device: str = "cpu"
    """`cpu` or `gpu:0`. CPU is the default: it needs no CUDA toolchain and the
    mobile models are fast enough. See README for the GPU path."""

    ocr_det_limit_side_len: int = 2560
    """Detection input is resized so its long side is at most this. Must be
    generous -- an upscaled A4 page is ~3500px and shrinking it back down
    defeats the point of upscaling."""

    ocr_text_score_thresh: float = 0.30
    """Drop recognitions below this. Deliberately low: for a review-driven
    workflow a wrong-but-visible value beats a silently dropped field."""

    ocr_use_doc_orientation_classify: bool = False
    ocr_use_doc_unwarping: bool = False
    ocr_use_textline_orientation: bool = False
    """All three off by default: these pages are axis-aligned digital
    rasterisations, so the extra models cost time and add failure modes."""

    ocr_workers: int = 1
    """Persistent worker process holding a warm PaddleOCR instance."""

    # ------------------------------------------------------- layout / cells
    expected_grid_cols: int = 3
    expected_grid_rows: int = 10
    grid_deviation_tolerance: float = 0.18
    """If detected cells deviate more than this fraction from the expected
    proportional grid, fall back to the proportional grid and flag the page."""

    min_cell_area_ratio: float = 0.010
    max_cell_area_ratio: float = 0.090
    """A record cell occupies roughly 1/30th (~3.3%) of the page body."""

    # ------------------------------------------------- template / matching
    label_fuzzy_threshold: int = 62
    """rapidfuzz score (0-100) for matching an OCR'd Tamil label. Low on
    purpose -- Tamil labels get mangled and a missed label loses the field."""

    default_template: str = "auto"
    """`auto` detects per page; or force `electoral_roll_ta` / `generic`."""

    # ------------------------------------------------ spelling consensus
    consensus_enabled: bool = True
    """Harmonise proper-noun spellings across a batch. See
    `services/consensus.py` for why this matters more than confidence
    filtering for Tamil names."""

    consensus_auto_apply: bool = True
    """Write the winning spelling to `edited_value`. `original_value` is
    never touched, and every change carries a SPELLING_VARIANT issue, so
    this stays fully reversible."""

    consensus_min_group: int = 3
    """Minimum total readings of a name before a vote is meaningful."""

    consensus_min_ratio: float = 3.0
    """The winner must outnumber the runner-up by this factor."""

    consensus_min_length: int = 3
    """Ignore very short values; too little signal to group safely."""

    # ------------------------------------------------------------- runtime
    cors_origins: str = "*"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.pages_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    try:
        s.ensure_dirs()
    except OSError:
        import tempfile
        s.data_dir = Path(tempfile.gettempdir()) / "data"
        s.ensure_dirs()
    return s


settings = get_settings()
