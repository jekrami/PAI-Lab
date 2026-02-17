import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


class RollingController:

    def __init__(self, train_window=100):
        self.train_window = train_window
        self.model = LogisticRegression()
        self.scaler = StandardScaler()
        self.trained = False

        self.feature_history = []
        self.outcome_history = []

        self.current_threshold = 0.65

    # -------------------------------------------------
    # Update history after trade closes
    # -------------------------------------------------

    def update_history(self, features, outcome):
        self.feature_history.append(features)
        self.outcome_history.append(outcome)

        if len(self.feature_history) > self.train_window:
            self.feature_history.pop(0)
            self.outcome_history.pop(0)

    # -------------------------------------------------
    # Retrain model if enough history
    # -------------------------------------------------

    def retrain_if_ready(self):

        if len(self.feature_history) < self.train_window:
            return

        X = pd.DataFrame(self.feature_history)
        y = pd.Series(self.outcome_history)

        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)

        self.trained = True

        self._update_threshold(X_scaled, y)

    # -------------------------------------------------
    # Adaptive threshold selection
    # -------------------------------------------------

    def _update_threshold(self, X_scaled, y):

        probs = self.model.predict_proba(X_scaled)[:, 1]

        best_threshold = 0.5
        best_expectancy = -999

        ATR_TARGET = 1.0
        ATR_STOP = 1.30

        for threshold in np.arange(0.5, 0.81, 0.05):

            mask = probs >= threshold
            if mask.sum() < 5:
                continue

            winrate = y[mask].mean()
            expectancy = (winrate * ATR_TARGET) - ((1 - winrate) * ATR_STOP)

            if expectancy > best_expectancy:
                best_expectancy = expectancy
                best_threshold = threshold

        self.current_threshold = best_threshold

    # -------------------------------------------------
    # Get decision for new trade
    # -------------------------------------------------

    def evaluate_trade(self, features):

        if not self.trained:
            return True  # allow trades until model ready

        X = pd.DataFrame([features])
        X_scaled = self.scaler.transform(X)

        prob = self.model.predict_proba(X_scaled)[0][1]

        return prob >= self.current_threshold
