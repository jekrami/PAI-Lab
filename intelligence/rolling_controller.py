# 2026-02-25 | v2.0.0 | Rolling ML Controller with Pattern Failure Memory | Writer: J.Ekrami | Co-writer: Antigravity
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

        # v5.0 — Pattern Failure Memory
        # Tracks last N outcomes per pattern type
        self.pattern_results    = {}   # { "h2": [1,0,1,...], "wedge": [...] }
        self.pattern_confidence = {}   # { "h2": 1.0, "wedge": 1.0, ... }

    # -------------------------------------------------
    # Update history after trade closes
    # -------------------------------------------------

    def update_history(self, features, outcome, pattern_type=None):
        self.feature_history.append(features)
        self.outcome_history.append(outcome)

        if len(self.feature_history) > self.train_window:
            self.feature_history.pop(0)
            self.outcome_history.pop(0)

        # v5.0: update pattern failure memory
        if pattern_type:
            results = self.pattern_results.setdefault(pattern_type, [])
            results.append(outcome)
            # Keep only last 10 outcomes per pattern
            if len(results) > 10:
                results.pop(0)

            # If last 2 are consecutive losses, halve confidence
            last2 = results[-2:] if len(results) >= 2 else []
            if last2 == [0, 0]:
                self.pattern_confidence[pattern_type] = 0.5
                # Only log outside warmup to avoid console noise
                if not getattr(self, "_warmup_mode", False):
                    print(f"[PatternMemory] Pattern '{pattern_type}' confidence halved (2x loss).")
            else:
                # Slowly recover confidence (cap at 1.0)
                current = self.pattern_confidence.get(pattern_type, 1.0)
                self.pattern_confidence[pattern_type] = min(1.0, current + 0.1)

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

    def evaluate_trade(self, features, signal_type=None):

        if not self.trained:
            return True  # allow trades until model ready

        X = pd.DataFrame([features])
        X_scaled = self.scaler.transform(X)

        prob = self.model.predict_proba(X_scaled)[0][1]

        # v5.0: Scale probability by pattern confidence before threshold check
        confidence = self.pattern_confidence.get(signal_type, 1.0) if signal_type else 1.0
        adjusted_prob = prob * confidence

        return adjusted_prob >= self.current_threshold
