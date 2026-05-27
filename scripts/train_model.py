"""Train and serialize the pin-scoring model.

Run:
    python scripts/train_model.py

This produces `data/scorer.joblib`, which is loaded by
`pin_service.scorer` at first inference.

Production: this script is replaced by a Kubeflow / Airflow pipeline
that pulls features from the feature store and ratings from the trips
warehouse. Here we generate synthetic data so the scaffold runs
end-to-end with zero external dependencies.
"""

from __future__ import annotations

import pathlib

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor


_OUT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "data" / "scorer.joblib"
)


def main(n_samples: int = 2000, seed: int = 0) -> None:
    rng = np.random.default_rng(seed)

    # Feature columns (must match scorer.py): walk_m, hour, hist, supply.
    walk_m = rng.gamma(shape=2.0, scale=40.0, size=n_samples)
    hour = rng.integers(0, 24, size=n_samples).astype(float)
    hist = rng.beta(a=5, b=2, size=n_samples)          # skewed toward 0.7+
    supply = rng.poisson(lam=4.0, size=n_samples).astype(float)

    X = np.stack([walk_m, hour, hist, supply], axis=1)

    # Synthetic label: rider satisfaction in roughly [-2, 2].
    # - Penalize long walks
    # - Reward high historical success
    # - Reward supply (proxy for short wait)
    # - Slight peak-hour penalty (more demand pressure)
    peak_penalty = np.where((hour >= 7) & (hour <= 9), 0.2, 0.0)
    peak_penalty += np.where((hour >= 17) & (hour <= 19), 0.2, 0.0)
    y = (
        -0.008 * walk_m
        + 1.5 * hist
        + 0.05 * supply
        - peak_penalty
        + rng.normal(scale=0.1, size=n_samples)
    )

    model = GradientBoostingRegressor(
        n_estimators=120, max_depth=3, learning_rate=0.08, random_state=seed
    )
    model.fit(X, y)

    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, _OUT_PATH)
    print(f"wrote {_OUT_PATH} ({_OUT_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"train R^2: {model.score(X, y):.3f}")


if __name__ == "__main__":
    main()
