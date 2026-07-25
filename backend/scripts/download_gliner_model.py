"""
Downloads a GLiNER biomedical NER model checkpoint locally, and builds
the model index that OpenMed's zero-shot toolkit needs to run inference.

Run this once, from the backend/ folder, with the venv activated:
    python scripts/download_gliner_model.py

Requires: pip install "openmed[gliner]" (already includes huggingface_hub)
"""

from pathlib import Path

from huggingface_hub import snapshot_download

# Smallest biomedical GLiNER checkpoint — chosen to run reasonably on CPU.
# If this later turns out too slow/inaccurate, "Ihor/gliner-biomed-base-v1.0"
# or "-large-v1.0" are drop-in alternatives, just heavier.
MODEL_REPO = "Ihor/gliner-biomed-small-v1.0"

MODELS_DIR = Path(__file__).parent.parent / "models"


def main():
    MODELS_DIR.mkdir(exist_ok=True)
    print(f"Downloading {MODEL_REPO} into {MODELS_DIR} ...")
    print("This downloads real model weights — it can take a few minutes")
    print("and needs a few hundred MB of free disk space.")

    local_path = snapshot_download(
        repo_id=MODEL_REPO,
        local_dir=MODELS_DIR / MODEL_REPO.replace("/", "__"),
    )
    print(f"Downloaded to: {local_path}")

    print("\nBuilding OpenMed's zero-shot model index ...")
    from openmed.ner import build_index, write_index

    index = build_index(MODELS_DIR)
    write_index(index, MODELS_DIR / "index.json", pretty=True)
    print(f"Index written to: {MODELS_DIR / 'index.json'}")
    print("\nOpen that file and check the 'id' field for each model —")
    print("that exact string is what you pass as model_id when calling the NER client.")


if __name__ == "__main__":
    main()
