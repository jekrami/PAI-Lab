# 2026-02-27 | Phase-2 v6.1 | AI Context Model Calibration | Writer: J.Ekrami | Co-writer: Antigravity
# v6.2.0
"""
Standalone AI module for regime context prediction.
Responsibilities:
    - Define, train, and calibrate the LightGBM/RandomForest classifiers
    - Predict bull_prob, bear_prob, trend_prob, continuation_prob
    - Use Platt Scaling (sigmoid) to guarantee monotonic probability calibrations
    - Handle model persistence & feature scaling
    - No training orchestration here (that is rolling_controller.py)
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
import joblib

# Optional: Use LightGBM if installed.
try:
    from lightgbm import LGBMClassifier
    _USE_LGBM = True
except ImportError:
    _USE_LGBM = False


class AIContextModel:
    """
    Phase-1 v6 Context AI.
    Predicts three regime targets:
        1. Bias    — {-1: Bear, 0: Neutral, 1: Bull}
        2. Env     — {0: Range, 1: Trend}
        3. Cont    — {0: Reversal, 1: Continuation}

    Always outputs calibrated probabilities, never hard classes directly.
    """

    def __init__(self):
        if _USE_LGBM:
            # LightGBM — preferred for speed and accuracy on tabular data
            base_bias = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.1,
                                             verbose=-1, random_state=42)
            base_env  = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.1,
                                             verbose=-1, random_state=42)
            base_cont = LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.1,
                                             verbose=-1, random_state=42)
        else:
            # RandomForest baseline if LightGBM not installed
            base_bias = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1)
            base_env  = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1)
            base_cont = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=-1)

        # Apply Platt Scaling via CalibratedClassifierCV for monotonic probability mapping
        self.model_bias = CalibratedClassifierCV(base_bias, method='sigmoid', cv=5)
        self.model_env  = CalibratedClassifierCV(base_env, method='sigmoid', cv=5)
        self.model_cont = CalibratedClassifierCV(base_cont, method='sigmoid', cv=5)

        self.scaler = StandardScaler()
        self.is_trained = False

        # Derived states after last predict_context() call
        self.last_context = {
            "bull_prob": 0.33,
            "bear_prob": 0.33,
            "trend_prob": 0.5,
            "continuation_prob": 0.5,
            "bias": "NEUTRAL",
            "environment": "TRANSITION"
        }

    def train(self, df_features: pd.DataFrame, df_labels: pd.DataFrame) -> bool:
        """
        Walk-forward training on a tabular snapshot.
        df_labels must contain columns: ['bias', 'env', 'cont']
        Returns True if training completed, False if not enough data.
        """
        if len(df_features) < 100:
            return False

        # Validate labels exist in the dataframe
        for col in ('bias', 'env', 'cont'):
            if col not in df_labels.columns:
                raise ValueError(f"AIContextModel.train(): df_labels is missing column '{col}'")

        # Scale features — fit on training data only
        X_scaled = self.scaler.fit_transform(df_features)

        self.model_bias.fit(X_scaled, df_labels['bias'])
        self.model_env.fit(X_scaled,  df_labels['env'])
        self.model_cont.fit(X_scaled, df_labels['cont'])

        self.is_trained = True
        return True

    def predict_context(self, features: dict) -> dict:
        """
        Predicts regime probabilities for the current bar.
        Always returns a dict with probabilities + derived Bias/Environment strings.
        Falls back to neutral context before warmup is complete.
        """
        if not self.is_trained:
            return dict(self.last_context)  # safe neutral defaults

        df_cur = pd.DataFrame([features])
        X_scaled = self.scaler.transform(df_cur)

        # --- Bias ---
        bias_classes   = list(self.model_bias.classes_)
        bias_probs_raw = self.model_bias.predict_proba(X_scaled)[0]
        bull_prob = bias_probs_raw[bias_classes.index(1)]  if  1 in bias_classes else 0.0
        bear_prob = bias_probs_raw[bias_classes.index(-1)] if -1 in bias_classes else 0.0

        # --- Environment ---
        env_classes   = list(self.model_env.classes_)
        env_probs_raw = self.model_env.predict_proba(X_scaled)[0]
        trend_prob = env_probs_raw[env_classes.index(1)] if 1 in env_classes else 0.5

        # --- Continuation ---
        cont_classes   = list(self.model_cont.classes_)
        cont_probs_raw = self.model_cont.predict_proba(X_scaled)[0]
        cont_prob = cont_probs_raw[cont_classes.index(1)] if 1 in cont_classes else 0.5

        # --- Derive discrete states ---
        if bull_prob > 0.6:
            bias = "BULL"
        elif bear_prob > 0.6:
            bias = "BEAR"
        else:
            bias = "NEUTRAL"

        if trend_prob > 0.6:
            environment = "TREND"
        elif trend_prob < 0.4:
            environment = "RANGE"
        else:
            environment = "TRANSITION"

        # --- Confidence: max probability across the dominant class of each model ---
        # Represents how strongly the AI 'believes' its own predictions.
        bias_conf = float(max(bias_probs_raw))
        env_conf  = float(max(env_probs_raw))
        cont_conf = float(max(cont_probs_raw))
        confidence = round((bias_conf + env_conf + cont_conf) / 3.0, 3)

        self.last_context = {
            "bull_prob":          round(bull_prob,  3),
            "bear_prob":          round(bear_prob,  3),
            "trend_prob":         round(trend_prob, 3),
            "continuation_prob":  round(cont_prob,  3),
            "confidence":         confidence,
            "bias":               bias,
            "environment":        environment
        }
        return dict(self.last_context)

    def save(self, model_path: str, scaler_path: str):
        """Saves the trained model and scaler to disk."""
        if not self.is_trained:
            raise RuntimeError("Cannot save an untrained model.")
        
        models = {
            "bias": self.model_bias,
            "env": self.model_env,
            "cont": self.model_cont
        }
        joblib.dump(models, model_path)
        joblib.dump(self.scaler, scaler_path)

    def load(self, model_path: str, scaler_path: str):
        """Loads the trained model and scaler from disk."""
        models = joblib.load(model_path)
        self.model_bias = models["bias"]
        self.model_env = models["env"]
        self.model_cont = models["cont"]
        
        self.scaler = joblib.load(scaler_path)
        self.is_trained = True
