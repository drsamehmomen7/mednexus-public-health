"""
Zero-shot NER using a locally downloaded GLiNER model.

We load GLiNER directly from the local model folder instead of going
through openmed.ner.infer(). Reason: infer() resolves model_id against
the HuggingFace Hub, so a local folder name like
"ihor__gliner-biomed-small-v1.0" is treated as a Hub repo id and fails
with a 401 RepositoryNotFound. Loading the folder directly keeps
everything offline and removes that whole failure mode.
"""

from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import List, Optional

# backend/models/ — where scripts/download_gliner_model.py puts checkpoints
MODELS_DIR = Path(environ.get(
    "OPENMED_ZEROSHOT_MODELS_DIR",
    Path(__file__).resolve().parent.parent.parent / "models",
))

# Cached across requests: loading the model takes seconds, so we do it once.
_model = None


@dataclass
class ExtractedEntity:
    label: str
    text: str
    score: float
    start: Optional[int] = None
    end: Optional[int] = None


class NerBackendUnavailable(RuntimeError):
    """Raised when the GLiNER package or local model folder is missing."""


def _find_model_dir() -> Path:
    """
    Find the downloaded GLiNER checkpoint folder inside MODELS_DIR.

    GLiNER checkpoints are marked by gliner_config.json (not the plain
    config.json that regular transformers models use), so we accept
    either, and search one level deep as well in case the download
    nested the files.
    """
    markers = ("gliner_config.json", "config.json")

    if not MODELS_DIR.exists():
        raise NerBackendUnavailable(
            f"Models folder not found: {MODELS_DIR}. "
            "Run: python scripts/download_gliner_model.py"
        )

    def is_checkpoint(folder: Path) -> bool:
        return any((folder / marker).exists() for marker in markers)

    if is_checkpoint(MODELS_DIR):
        return MODELS_DIR

    for candidate in sorted(MODELS_DIR.iterdir()):
        if candidate.is_dir():
            if is_checkpoint(candidate):
                return candidate
            for nested in sorted(candidate.iterdir()):
                if nested.is_dir() and is_checkpoint(nested):
                    return nested

    # Include the actual folder contents in the error — guessing blind at
    # what is on disk is what made this slow to diagnose the first time.
    found = [str(p.relative_to(MODELS_DIR)) for p in sorted(MODELS_DIR.rglob("*"))][:40]
    raise NerBackendUnavailable(
        f"No GLiNER checkpoint found inside {MODELS_DIR}. "
        f"Looked for {' or '.join(markers)}. "
        f"Contents found: {found}"
    )


def _load_model():
    """Load the GLiNER model once and reuse it for later requests."""
    global _model
    if _model is not None:
        return _model

    try:
        from gliner import GLiNER
    except ImportError as exc:
        raise NerBackendUnavailable(
            'GLiNER is not installed. Run: pip install "openmed[gliner]"'
        ) from exc

    model_dir = _find_model_dir()
    # local_files_only: never reach out to the HuggingFace Hub. This is what
    # the previous 401 error was — an unwanted network lookup.
    _model = GLiNER.from_pretrained(str(model_dir), local_files_only=True)
    return _model


def extract_entities(
    text: str,
    labels: List[str],
    domain: str = "biomedical",
    model_id: Optional[str] = None,
    threshold: float = 0.5,
) -> List[ExtractedEntity]:
    """
    Run zero-shot NER over `text`, looking for the given entity `labels`.

    `domain` and `model_id` are accepted but unused — kept so the call
    signature stays stable for callers and tests.
    """
    model = _load_model()
    predictions = model.predict_entities(text, labels, threshold=threshold)

    return [
        ExtractedEntity(
            label=item["label"],
            text=item["text"],
            score=float(item.get("score", 0.0)),
            start=item.get("start"),
            end=item.get("end"),
        )
        for item in predictions
    ]
