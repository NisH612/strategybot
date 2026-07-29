from pathlib import Path

import numpy as np

from src.database import Database
from src.utils.logger import logger


class MLDataPreparer:
    def __init__(self, db: Database) -> None:
        self.db = db

    def export_csv(self, output_path: Path) -> None:
        self.db.export_market_data_csv(output_path)

    def build_feature_matrix(self, lookback: int = 10) -> tuple[np.ndarray, np.ndarray]:
        rows = self.db.get_market_data(limit=10000)
        if len(rows) < lookback + 5:
            logger.warning("Not enough data for feature matrix (%d rows)", len(rows))
            return np.array([]), np.array([])

        rows = list(reversed(rows))
        X, y = [], []
        for i in range(lookback, len(rows) - 1):
            features = []
            for j in range(i - lookback, i):
                r = rows[j]
                features.extend([
                    r.price,
                    r.ema_fast,
                    r.ema_slow,
                    r.ema_trend,
                    r.volume,
                    r.open_interest,
                    r.funding_rate,
                    r.long_short_ratio,
                    r.fear_greed_value,
                    r.btc_dominance,
                    r.sentiment_score,
                ])
            target = 1 if rows[i + 1].price > rows[i].price else 0
            X.append(features)
            y.append(target)

        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int64)
        logger.info("Feature matrix: %s shape, %d samples", X.shape, len(y))
        return X, y

    def normalize(self, X: np.ndarray) -> np.ndarray:
        if X.size == 0:
            return X
        means = np.nanmean(X, axis=0)
        stds = np.nanstd(X, axis=0)
        stds[stds == 0] = 1.0
        return (X - means) / stds

    def handle_missing(self, X: np.ndarray) -> np.ndarray:
        return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
