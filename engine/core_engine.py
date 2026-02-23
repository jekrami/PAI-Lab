# 2026-02-24 | v3.0.0 | Core signal and feature engine | Writer: J.Ekrami | Co-writer: Antigravity
"""
core_engine.py

Core signal and feature generation logic.

This module:
- Detects structural signals (H2/L2, H1/L1, wedges, breakouts, inside bars, failed breakouts)
- Suppresses signals during climactic exhaustion (with 5-bar cooldown)
- Enforces Prior Day H/L and Opening Range as hard S/R filters
- Blocks outside bars without strong follow-through
- Supports follow-through confirmation (Phase 2)
- Builds features
- Does NOT resolve trades
- Does NOT simulate exits
- Does NOT connect to live feed

It is shared by:
- Backtest mode
- Live mode
"""

from config import *
from core.feature_extractor import extract_features
from core.session_context import SessionContext
from pai_engine import (
    MarketMemory,
    TrendAnalyzer,
    PriceActionAnalyzer,
    SecondEntryDetector,
    FirstEntryDetector,
    WedgeDetector,
    MarketEnvironmentClassifier,
    BreakoutDetector,
    InsideBarDetector,
    SwingPivotTracker,
)


class CoreEngine:

    def __init__(self, asset_config=None):
        self.memory = MarketMemory(maxlen=100)
        self.pending_signal = None          # Phase 2: follow-through confirmation
        self.exhaustion_cooldown = 0        # bars remaining in post-climactic cooldown
        self.pending_breakout = None        # for Failed Breakout detection
        # Session context for session-aware filtering
        session_str = (asset_config or {}).get("session", "24/7")
        self.session_ctx = SessionContext(session_str=session_str)
        self.bars_since_session_open = 0    # suppress first 2 bars of each new session
        self._last_session_date = None      # track session day changes

    # -------------------------------------------------
    # Add new candle to memory
    # -------------------------------------------------

    def add_candle(self, candle):
        self.memory.add(candle)
        # Update session context for every candle
        self.session_ctx.update(candle)
        # Track session open (for London/NY open suppression)
        candle_date = None
        try:
            from datetime import datetime, timedelta
            t = candle.get("time") or candle.get("open_time")
            if isinstance(t, (int, float)):
                candle_date = datetime.utcfromtimestamp(t / 1000).date()
            else:
                candle_date = t.date() if hasattr(t, 'date') else None
        except Exception:
            pass
        if candle_date and candle_date != self._last_session_date:
            self._last_session_date = candle_date
            self.bars_since_session_open = 0
        else:
            self.bars_since_session_open += 1

    # -------------------------------------------------
    # Detect signal
    # -------------------------------------------------

    def detect_signal(self):

        mem = self.memory.data()

        if len(mem) < 50:
            self.pending_signal = None
            return None

        # --- Session Window Enforcement (Al Brooks: only trade during active session) ---
        session_str = (self.session_ctx.session_str or "24/7").strip()
        if session_str != "24/7":
            try:
                from datetime import datetime, timedelta
                EST_OFFSET = timedelta(hours=-5)
                t = mem[-1].get("time") or mem[-1].get("open_time")
                dt_est = (datetime.utcfromtimestamp(t / 1000) if isinstance(t, (int, float)) else t) + EST_OFFSET
                time_part = session_str.split("_")[0]
                start_str, end_str = time_part.split("-")
                sh, sm = int(start_str.split(":")[0]), int(start_str.split(":")[1])
                eh, em = int(end_str.split(":")[0]), int(end_str.split(":")[1])
                bar_min = dt_est.hour * 60 + dt_est.minute
                if not (sh * 60 + sm <= bar_min < eh * 60 + em):
                    return None
            except Exception:
                pass  # malformed config: fail open

        # --- Suppress first 2 bars of each new session (London/NY open avoidance) ---
        if self.bars_since_session_open < 2:
            return None

        # --- Follow-Through Confirmation (Phase 2) ---
        if self.pending_signal is not None:
            pending = self.pending_signal
            self.pending_signal = None  # consume it

            ft_bar = mem[-1]
            ft_rng = ft_bar["high"] - ft_bar["low"]
            if ft_rng > 0:
                ft_body = abs(ft_bar["close"] - ft_bar["open"])
                ft_close_pos = (ft_bar["close"] - ft_bar["low"]) / ft_rng
                ft_body_ratio = ft_body / ft_rng

                if pending["direction"] == "bullish":
                    if ft_close_pos > 0.5 and ft_body_ratio > 0.3:
                        return pending
                elif pending["direction"] == "bearish":
                    if ft_close_pos < 0.5 and ft_body_ratio > 0.3:
                        return pending

            return None

        trend = TrendAnalyzer.analyze(mem)
        pa = PriceActionAnalyzer.trend_bar_info(mem)
        env = MarketEnvironmentClassifier.classify(mem, trend, pa)

        # --- Always-In Direction via Swing Pivots (Al Brooks: not a slope, but structural pivots) ---
        # Use as the primary gating direction, falling back to TrendAnalyzer if pivots are neutral.
        pivot_direction = SwingPivotTracker.always_in_direction(mem)
        bias = pivot_direction if pivot_direction != "neutral" else trend["direction"]

        if env == "tight_trading_range":
            return "tight_trading_range"

        # --- Post-Climactic Cooldown (Al Brooks: market needs reset after exhaustion) ---
        if pa.get("climactic", False):
            self.exhaustion_cooldown = 5   # block next 5 bars
        if self.exhaustion_cooldown > 0:
            self.exhaustion_cooldown -= 1
            return None

        # --- Outside Bar Hard Block (Al Brooks: outside bars create confusion) ---
        if pa.get("is_outside_bar", False):
            # Store as pending — only unblock if next bar breaks cleanly outside it
            # For simplicity: block any new setup generation on an outside bar
            return None

        # ---------------------------------------------------------------
        # Failed Breakout Detector (check before H2/L2 — time-critical)
        # ---------------------------------------------------------------
        last = mem[-1]
        if self.pending_breakout is not None:
            pb = self.pending_breakout
            self.pending_breakout = None  # consume

            last_rng = last["high"] - last["low"]
            last_body = abs(last["close"] - last["open"])
            if last_rng > 0:
                last_body_ratio = last_body / last_rng
                last_close_pos = (last["close"] - last["low"]) / last_rng

                if pb["direction"] == "bull_breakout":
                    # Failure: closes back below the breakout bar's close with a bear body
                    if last["close"] < pb["bar"]["close"] and last_body_ratio > 0.4 and last_close_pos < 0.4:
                        # Bearish fade — NO follow-through needed, failure IS the confirmation
                        return {
                            "type": "failed_breakout",
                            "direction": "bearish",
                            "time": last["time"],
                            "price": last["close"],
                            "pullback_depth": pb["bar"]["high"] - last["low"],
                            "pullback_bars": 1,
                        }
                elif pb["direction"] == "bear_breakout":
                    if last["close"] > pb["bar"]["close"] and last_body_ratio > 0.4 and last_close_pos > 0.6:
                        return {
                            "type": "failed_breakout",
                            "direction": "bullish",
                            "time": last["time"],
                            "price": last["close"],
                            "pullback_depth": last["high"] - pb["bar"]["low"],
                            "pullback_bars": 1,
                        }

        # --- H2 / L2 Second Entry Detection ---
        signal = SecondEntryDetector.detect(mem, bias, pa)

        if signal:
            if signal["direction"] == "bullish" and env == "structural_bull_trend":
                self.pending_signal = signal
                return None
            if signal["direction"] == "bearish" and env == "structural_bear_trend":
                self.pending_signal = signal
                return None

        # --- H1 / L1 First Entry (strong trends only) ---
        h1_signal = FirstEntryDetector.detect(mem, bias, pa)
        if h1_signal:
            if h1_signal["direction"] == "bullish" and env == "structural_bull_trend":
                self.pending_signal = h1_signal
                return None
            if h1_signal["direction"] == "bearish" and env == "structural_bear_trend":
                self.pending_signal = h1_signal
                return None

        # --- Wedge / 3-Push Reversal (counter-trend) ---
        wedge = WedgeDetector.detect(mem, trend["direction"])
        if wedge:
            self.pending_signal = wedge
            return None

        # --- Inside Bar Setup (Al Brooks: compression before continuation) ---
        ib_signal = InsideBarDetector.detect(mem, trend["direction"])
        if ib_signal:
            if ib_signal["direction"] == "bullish" and env in ("structural_bull_trend",):
                self.pending_signal = ib_signal
                return None
            if ib_signal["direction"] == "bearish" and env in ("structural_bear_trend",):
                self.pending_signal = ib_signal
                return None

        # --- Breakout Detection (and register for potential failure next bar) ---
        breakout = BreakoutDetector.detect(mem, trend["direction"])

        if breakout == "bull_breakout" and env in ("structural_bull_trend", "trading_range"):
            last_rng = last["high"] - last["low"]
            if last_rng > 0:
                close_pos = (last["close"] - last["low"]) / last_rng
                body_ratio = abs(last["close"] - last["open"]) / last_rng
                if close_pos > 0.6 and body_ratio > 0.4:
                    # Register for failed-breakout check next bar
                    self.pending_breakout = {"direction": "bull_breakout", "bar": last}
                    return {
                        "type": "breakout",
                        "direction": "bullish",
                        "time": last["time"],
                        "price": last["close"],
                        "pullback_depth": last_rng,
                        "pullback_bars": 1,
                    }

        if breakout == "bear_breakout" and env in ("structural_bear_trend", "trading_range"):
            last_rng = last["high"] - last["low"]
            if last_rng > 0:
                close_pos = (last["close"] - last["low"]) / last_rng
                body_ratio = abs(last["close"] - last["open"]) / last_rng
                if close_pos < 0.4 and body_ratio > 0.4:
                    self.pending_breakout = {"direction": "bear_breakout", "bar": last}
                    return {
                        "type": "breakout",
                        "direction": "bearish",
                        "time": last["time"],
                        "price": last["close"],
                        "pullback_depth": last_rng,
                        "pullback_bars": 1,
                    }

        return None

    # -------------------------------------------------
    # Build features for probability model
    # -------------------------------------------------

    def build_features(self, signal, asset_config=None):

        mem = self.memory.data()

        ranges = [c["high"] - c["low"] for c in mem[-14:]]
        atr = sum(ranges) / len(ranges)

        # For breakout / failed-breakout signals, skip strict pullback depth/duration filters
        if signal.get("type") in ("breakout", "failed_breakout"):
            long_ranges = [c["high"] - c["low"] for c in mem[-50:]]
            long_atr = sum(long_ranges) / len(long_ranges)
            signal_bar = mem[-1]
            features = extract_features(mem, signal, atr, long_atr, signal_bar, signal_bar, asset_config=asset_config)
            return features, atr

        if atr > 0 and signal["pullback_depth"] / atr < DEPTH_THRESHOLD_ATR:
            return None

        pullback_bars = signal["pullback_bars"]
        if signal.get("type") != "inside_bar_entry":
            if not (PULLBACK_MIN <= pullback_bars <= PULLBACK_MAX):
                return None

        long_ranges = [c["high"] - c["low"] for c in mem[-50:]]
        long_atr = sum(long_ranges) / len(long_ranges)

        signal_bar = mem[-1]

        features = extract_features(mem, signal, atr, long_atr, signal_bar, signal_bar, asset_config=asset_config)

        # --- HOD/LOD Hard Filter ---
        if signal.get("direction") == "bullish" and features.get("dist_to_hod_atr", 999) < 0.5:
            return None
        if signal.get("direction") == "bearish" and features.get("dist_to_lod_atr", 999) < 0.5:
            return None

        # --- Prior Day H/L Hard Filter (Al Brooks: don't buy at PDH or sell at PDL) ---
        if signal.get("direction") == "bullish" and features.get("dist_to_pdh_atr", 999) < 0.5:
            return None
        if signal.get("direction") == "bearish" and features.get("dist_to_pdl_atr", 999) < 0.5:
            return None

        # --- Opening Range Hard Filter (Al Brooks: ORH/ORL act as S/R) ---
        if signal.get("direction") == "bullish" and features.get("dist_to_orh_atr", 999) < 0.3:
            return None
        if signal.get("direction") == "bearish" and features.get("dist_to_orl_atr", 999) < 0.3:
            return None

        # --- Extra ML features from signal metadata ---
        features["micro_double"] = 1.0 if signal.get("micro_double") else 0.0
        features["is_third_entry"] = 1.0 if signal.get("type") == "third_entry" else 0.0

        return features, atr
