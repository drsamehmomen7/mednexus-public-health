"""
One-time (rerun as needed) builder for data/notifiable_diseases.json —
the seed vocabulary for the disease gazetteer, until a real deployment
supplies its own reportable-disease list the way it supplies
population_strata for region.

Source: the distinct, non-"Unknown" disease_name values in the synthetic
ground truth — the closest thing this project currently has to a
deployment-supplied notifiable-disease list. Swap this for a real
ministry list later; nothing downstream cares where the list came from.
"""
import json
from pathlib import Path

GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent / "data" / "synthetic_reports" / "ground_truth.json"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "notifiable_diseases.json"


def main() -> None:
    data = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))

    # Real shape (confirmed against the actual file): a list of records,
    # each {"file": ..., "text": ..., "truth": {"disease_name": ..., ...}}.
    # The ground-truth fields live under "truth", not on the record itself.
    diseases = sorted({
        r["truth"]["disease_name"]
        for r in data
        if isinstance(r, dict)
        and isinstance(r.get("truth"), dict)
        and r["truth"].get("disease_name")
        and r["truth"]["disease_name"] != "Unknown"
    })

    OUT_PATH.write_text(json.dumps(diseases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(diseases)} diseases to {OUT_PATH}")
    for d in diseases:
        print(f"  - {d}")


if __name__ == "__main__":
    main()
