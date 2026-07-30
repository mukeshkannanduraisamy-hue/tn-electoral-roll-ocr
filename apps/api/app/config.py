"""Central configuration, loaded from environment with sane defaults.

Every tunable that affects OCR quality lives here so it can be adjusted
without touching code -- see `.env.example` for the documented set.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = .../apps/api/app/config.py -> up 4 levels
_current_path = Path(__file__).resolve()
# Fall back to parents[1] (/app) if the directory tree is flat inside Docker
REPO_ROOT = _current_path.parents[3] if len(_current_path.parents) > 3 else _current_path.parents[1]


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
    ocr_performance_mode: str = "turbo"
    """`turbo` (fastest), `balanced`, or `max_accuracy`."""

    upscale_factor: float = 1.5
    """Bicubic upscale applied before OCR. Source scans are ~144 DPI; 1.5x provides
    ample resolution for Tamil glyphs while maintaining low pixel volume."""

    denoise_enabled: bool = True
    denoise_strength: int = 7
    """`h` parameter for cv2.fastNlMeansDenoising in max_accuracy mode. Applied
    BEFORE CLAHE so contrast enhancement doesn't amplify paper grain."""

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

    ocr_det_limit_side_len: int = 1536
    """Detection input is resized so its long side is at most this."""

    ocr_text_score_thresh: float = 0.30
    """Drop recognitions below this. Deliberately low: for a review-driven
    workflow a wrong-but-visible value beats a silently dropped field."""

    ocr_use_doc_orientation_classify: bool = False
    ocr_use_doc_unwarping: bool = False
    ocr_use_textline_orientation: bool = False
    """All three off by default: these pages are axis-aligned digital
    rasterisations, so the extra models cost time and add failure modes."""

    ocr_workers: int = Field(
        default_factory=lambda: max(1, min(os.cpu_count() or 2, 8))
    )
    """Persistent worker processes, each holding a warm PaddleOCR instance."""

    max_retries: int = 3
    """Maximum automatic retry attempts per page if OCR or rendering encounters a transient error."""

    enable_caching: bool = True
    """Skip re-extracting pages whose file hash and page parameters match cached extraction outputs."""

    auto_gpu: bool = True
    """Automatically detect CUDA GPU availability and switch PaddleOCR device to GPU when present."""

    batch_ocr_size: int = 4
    """Batch size for processing image crops / pages in parallel."""

    ocr_det_model: str = "PP-OCRv5_mobile_det"
    """Override the text-detection model to `PP-OCRv5_mobile_det` for low memory footprint."""

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

    # ---------------------------------------------------------- auth
    auth_enabled: bool = True
    """Set false ONLY for local development. When off, every endpoint is
    open to anyone who can reach the port."""

    admin_username: str = "admin"

    admin_password: str = "Admin@123456"
    """Initial admin password, used once at first boot."""

    auth_session_hours: int = 720

    auth_min_password_length: int = 10

    auth_max_failed_attempts: int = 8
    auth_lockout_minutes: int = 15
    """Locks a username after repeated failures so it cannot be brute-forced."""

    auth_cookie_secure: bool = False
    """Send the session cookie only over HTTPS. MUST be true in production;
    false locally because dev runs on plain http://localhost."""

    # ---------------------------------------------------------- reports
    pdf_font_path: str = ""
    """TTF/TTC with Tamil coverage, for PDF export.

    Auto-detected when empty. ReportLab's built-in fonts have no Tamil
    glyphs, so without a real font every name renders as empty boxes --
    which looks like working software while silently producing unusable
    reports. See `services/voter_export.resolve_font`."""

    # ------------------------------------------------------------- runtime
    cors_origins: str = "*"
    """Comma-separated allowed origins. A bare hostname is accepted and gets
    a scheme applied (see `main._cors_origins`), because Render's
    `fromService: property: host` injects hostnames without one."""

    allow_folder_import: bool = True
    """Enable `POST /api/files/import-folder`.

    That endpoint registers PDFs straight off the server's filesystem, which
    is exactly what you want when the corpus is already on the same machine
    -- and exactly what you do not want on a public host, where it lets a
    caller probe for readable paths. Disabled in the Render blueprint.
    """

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    @property
    def photos_dir(self) -> Path:
        """Crops taken off page images: station imagery and voter photos."""
        return self.data_dir / "photos"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.pages_dir, self.photos_dir):
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
