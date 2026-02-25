# 2026-02-25 | v5.0.0 | Context-Aware Core signal engine | Writer: J.Ekrami | Co-writer: Antigravity
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

        # v5.0 — Breakout state machine
        self.breakout_state = None          # None | "ACTIVE"
        self.breakout_bar = None            # the bar at which breakout was confirmed
        self.breakout_bars_elapsed = 0      # bars since breakout became ACTIVE

        # v5.0 — Major Trend Reversal (MTR) state machine
        self.mtr_state = None               # None | "TEST_EXTREME" | "REVERSAL_ATTEMPT"
        self.mtr_extreme = None             # price of the prior extreme being tested

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
            from datetime import datetime, timedelta, timezone
            t = candle.get("time") or candle.get("open_time")
            if isinstance(t, (int, float)):
                candle_date = datetime.fromtimestamp(t / 1000, timezone.utc).date()
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
    # Pressure Score (v5.0 — replaces 3 binary filters)
    # -------------------------------------------------

    def _compute_pressure_score(self, bar, mem):
        """
        Composite directional pressure (0–5).
        Replaces hard binary checks: body_ratio > 0.4, close_pos > 0.65, body > 1.2*avg_body
        """
        score = 0
        rng = bar["high"] - bar["low"]
        if rng == 0:
            return 0

        close_pos = (bar["close"] - bar["low"]) / rng
        body = abs(bar["close"] - bar["open"])
        body_ratio = body / rng

        # 1. Close near extreme
        if close_pos > 0.70 or close_pos < 0.30:
            score += 1

        # 2. Consecutive directional closes (>= 2)
        if len(mem) >= 3:
            c1 = mem[-1]["close"] > mem[-2]["close"]
            c2 = mem[-2]["close"] > mem[-3]["close"]
            if c1 and c2:   # bullish
                score += 1
            elif not c1 and not c2:  # bearish
                score += 1

        # 3. Range expansion
        avg_ranges = [c["high"] - c["low"] for c in mem[-10:] if c != bar]
        if avg_ranges:
            avg_rng = sum(avg_ranges) / len(avg_ranges)
            if rng > avg_rng:
                score += 1

        # 4. Low overlap with prior bar
        if len(mem) >= 2:
            prev = mem[-2]
            overlap = min(bar["high"], prev["high"]) - max(bar["low"], prev["low"])
            overlap_ratio = max(0, overlap) / rng
            if overlap_ratio < 0.3:
                score += 1

        # 5. Dominant tail rejection on opposite side
        upper_tail = bar["high"] - max(bar["open"], bar["close"])
        lower_tail = min(bar["open"], bar["close"]) - bar["low"]
        if close_pos > 0.5 and lower_tail > 0.3 * body:
            score += 1   # bull bar with strong lower wick rejection
        elif close_pos < 0.5 and upper_tail > 0.3 * body:
            score += 1   # bear bar with strong upper wick rejection

        return score

    # -------------------------------------------------
    # Regime Probability Score (v5.0 — replaces binary env string)
    # -------------------------------------------------

    def _compute_regime_probability(self, mem, pressure_score, env):
        """
        Returns a float 0.0 (pure range) to 1.0 (pure trend).
        Based on pressure + structure + overlap scoring.
        """
        # Structure score: how many recent bars make new HH/LL
        structure_score = 0
        for i in range(1, min(6, len(mem))):
            if mem[-i]["close"] > mem[-i-1]["high"]:
                structure_score += 1
            elif mem[-i]["close"] < mem[-i-1]["low"]:
                structure_score += 1

        # Overlap score: proportion of overlapping bars in last 10
        overlap_count = 0
        for i in range(1, min(10, len(mem))):
            lo = min(mem[-i]["high"], mem[-i-1]["high"])
            hi = max(mem[-i]["low"], mem[-i-1]["low"])
            if lo > hi:
                overlap_count += 1
        overlap_score = overlap_count

        # Failed breakout history (use pending_breakout as proxy)
        failed_score = 1 if self.pending_breakout is None else 0

        trend_score = pressure_score + structure_score
        range_score = overlap_score + failed_score
        denom = trend_score + range_score
        if denom == 0:
            return 0.5

        prob = trend_score / denom

        # Align with explicit env labels
        if env in ("structural_bull_trend", "structural_bear_trend"):
            prob = max(0.6, prob)
        elif env in ("tight_trading_range", "trading_range"):
            prob = min(0.4, prob)

        return round(min(1.0, max(0.0, prob)), 3)

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
                from datetime import datetime, timedelta, timezone
                EST_OFFSET = timedelta(hours=-5)
                t = mem[-1].get("time") or mem[-1].get("open_time")
                dt_est = (datetime.fromtimestamp(t / 1000, timezone.utc) if isinstance(t, (int, float)) else t) + EST_OFFSET
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

        # --- Always-In Direction via Swing Pivots ---
        pivot_direction = SwingPivotTracker.always_in_direction(mem)
        bias = pivot_direction if pivot_direction != "neutral" else trend["direction"]

        if env == "tight_trading_range":
            return "tight_trading_range"

        # --- Pressure Scoring (v5.0: replaces body_ratio/close_pos/body hard checks) ---
        last = mem[-1]
        pressure_score = self._compute_pressure_score(last, mem)
        if pressure_score < 3:
            # Signal bar lacks directional conviction
            return None

        # --- Regime Probability Score (v5.0: replaces binary env string) ---
        regime_probability = self._compute_regime_probability(mem, pressure_score, env)

        # --- Volatility Shock Compression (v5.0) ---
        ranges_14 = [c["high"] - c["low"] for c in mem[-14:]]
        atr = sum(ranges_14) / len(ranges_14) if ranges_14 else 1
        signal_bar_range = last["high"] - last["low"]
        atr_ratio = signal_bar_range / atr if atr > 0 else 0

        force_scalp = False
        risk_override = None
        if atr_ratio > 2.0:
            # Hard block: oversized risk on current bar
            return None
        elif atr_ratio > 1.5:
            force_scalp = True
            risk_override = 0.003

        # --- MTR Protocol State Machine (v5.0) ---
        if len(mem) >= 20:
            recent_highs = [c["high"] for c in mem[-20:]]
            recent_lows  = [c["low"]  for c in mem[-20:]]
            prior_high = max(recent_highs[:-5])
            prior_low  = min(recent_lows[:-5])

            # Detect trend break: new low in bull trend or new high in bear trend
            if bias == "bullish" and last["close"] < prior_low:
                self.mtr_state = "TEST_EXTREME"
                self.mtr_extreme = prior_low
            elif bias == "bearish" and last["close"] > prior_high:
                self.mtr_state = "TEST_EXTREME"
                self.mtr_extreme = prior_high

            # Advance to REVERSAL_ATTEMPT if the bar fails to make a new extreme
            if self.mtr_state == "TEST_EXTREME":
                if bias == "bullish" and last["low"] > self.mtr_extreme:
                    self.mtr_state = "REVERSAL_ATTEMPT"
                elif bias == "bearish" and last["high"] < self.mtr_extreme:
                    self.mtr_state = "REVERSAL_ATTEMPT"

        # --- Post-Climactic Cooldown ---
        if pa.get("climactic", False):
            self.exhaustion_cooldown = 5
        if self.exhaustion_cooldown > 0:
            self.exhaustion_cooldown -= 1
            return None

        # --- Outside Bar Hard Block ---
        if pa.get("is_outside_bar", False):
            return None

        # ---------------------------------------------------------------
        # Failed Breakout Detector
        # ---------------------------------------------------------------
        if self.pending_breakout is not None:
            pb = self.pending_breakout
            self.pending_breakout = None

            last_rng = last["high"] - last["low"]
            last_body = abs(last["close"] - last["open"])
            if last_rng > 0:
                last_body_ratio = last_body / last_rng
                last_close_pos = (last["close"] - last["low"]) / last_rng

                if pb["direction"] == "bull_breakout":
                    if last["close"] < pb["bar"]["close"] and last_body_ratio > 0.4 and last_close_pos < 0.4:
                        sig = {
                            "type": "failed_breakout",
                            "direction": "bearish",
                            "time": last["time"],
                            "price": last["close"],
                            "pullback_depth": pb["bar"]["high"] - last["low"],
                            "pullback_bars": 1,
                            "regime_probability": regime_probability,
                            "pressure_score": pressure_score,
                        }
                        if force_scalp:
                            sig["force_scalp"] = True
                            sig["risk_override"] = risk_override
                        # Clear breakout state on failure
                        self.breakout_state = None
                        return sig
                elif pb["direction"] == "bear_breakout":
                    if last["close"] > pb["bar"]["close"] and last_body_ratio > 0.4 and last_close_pos > 0.6:
                        sig = {
                            "type": "failed_breakout",
                            "direction": "bullish",
                            "time": last["time"],
                            "price": last["close"],
                            "pullback_depth": last["high"] - pb["bar"]["low"],
                            "pullback_bars": 1,
                            "regime_probability": regime_probability,
                            "pressure_score": pressure_score,
                        }
                        if force_scalp:
                            sig["force_scalp"] = True
                            sig["risk_override"] = risk_override
                        self.breakout_state = None
                        return sig

        # --- Breakout State Machine (v5.0) ---
        if self.breakout_state == "ACTIVE":
            self.breakout_bars_elapsed += 1
            # Timeout: if no follow-through in 10 bars, clear state
            if self.breakout_bars_elapsed > 10:
                self.breakout_state = None
                self.breakout_bar = None
            else:
                # Look for pullback entry
                prev = mem[-2] if len(mem) >= 2 else None
                if prev and self.breakout_bar:
                    bo_dir = self.breakout_bar.get("breakout_dir", "bull")
                    # Simple pullback: bar pulls back from breakout direction
                    if bo_dir == "bull" and last["low"] < prev["low"] and last["close"] > last["open"]:
                        sig = {
                            "type": "breakout_pullback",
                            "direction": "bullish",
                            "time": last["time"],
                            "price": last["close"],
                            "pullback_depth": prev["high"] - last["low"],
                            "pullback_bars": 2,
                            "regime_probability": regime_probability,
                            "pressure_score": pressure_score,
                        }
                        self.breakout_state = None
                        return sig
                    elif bo_dir == "bear" and last["high"] > prev["high"] and last["close"] < last["open"]:
                        sig = {
                            "type": "breakout_pullback",
                            "direction": "bearish",
                            "time": last["time"],
                            "price": last["close"],
                            "pullback_depth": last["high"] - prev["low"],
                            "pullback_bars": 2,
                            "regime_probability": regime_probability,
                            "pressure_score": pressure_score,
                        }
                        self.breakout_state = None
                        return sig

        # --- H2 / L2 Second Entry Detection ---
        signal = SecondEntryDetector.detect(mem, bias, pa)

        if signal:
            # MTR Gate: block counter-trend trades unless reversal is confirmed
            if signal["direction"] == "bearish" and bias == "bullish" and self.mtr_state != "REVERSAL_ATTEMPT":
                signal = None
            elif signal["direction"] == "bullish" and bias == "bearish" and self.mtr_state != "REVERSAL_ATTEMPT":
                signal = None

        if signal:
            signal["regime_probability"] = regime_probability
            signal["pressure_score"] = pressure_score
            if force_scalp:
                signal["force_scalp"] = True
                signal["risk_override"] = risk_override
            if signal["direction"] == "bullish" and env == "structural_bull_trend":
                self.pending_signal = signal
                return None
            if signal["direction"] == "bearish" and env == "structural_bear_trend":
                self.pending_signal = signal
                return None

        # --- H1 / L1 First Entry (strong trends only) ---
        h1_signal = FirstEntryDetector.detect(mem, bias, pa)
        if h1_signal:
            h1_signal["regime_probability"] = regime_probability
            h1_signal["pressure_score"] = pressure_score
            if force_scalp:
                h1_signal["force_scalp"] = True
                h1_signal["risk_override"] = risk_override
            if h1_signal["direction"] == "bullish" and env == "structural_bull_trend":
                self.pending_signal = h1_signal
                return None
            if h1_signal["direction"] == "bearish" and env == "structural_bear_trend":
                self.pending_signal = h1_signal
                return None

        # --- Wedge / 3-Push Reversal (counter-trend) ---
        # MTR gate: require REVERSAL_ATTEMPT for counter-trend wedges
        wedge = WedgeDetector.detect(mem, trend["direction"])
        if wedge:
            is_counter = (wedge["direction"] == "bullish" and bias == "bearish") or \
                         (wedge["direction"] == "bearish" and bias == "bullish")
            if is_counter and self.mtr_state != "REVERSAL_ATTEMPT":
                wedge = None
        if wedge:
            wedge["regime_probability"] = regime_probability
            wedge["pressure_score"] = pressure_score
            self.pending_signal = wedge
            return None

        # --- Inside Bar Setup ---
        ib_signal = InsideBarDetector.detect(mem, trend["direction"])
        if ib_signal:
            ib_signal["regime_probability"] = regime_probability
            ib_signal["pressure_score"] = pressure_score
            if ib_signal["direction"] == "bullish" and env in ("structural_bull_trend",):
                self.pending_signal = ib_signal
                return None
            if ib_signal["direction"] == "bearish" and env in ("structural_bear_trend",):
                self.pending_signal = ib_signal
                return None

        # --- Breakout Detection (register state machine + signal) ---
        breakout = BreakoutDetector.detect(mem, trend["direction"])

        if breakout == "bull_breakout" and env in ("structural_bull_trend", "trading_range"):
            last_rng = last["high"] - last["low"]
            if last_rng > 0:
                close_pos = (last["close"] - last["low"]) / last_rng
                if close_pos > 0.6 and pressure_score >= 3:
                    # Register for failed-breakout check next bar
                    self.pending_breakout = {"direction": "bull_breakout", "bar": last}
                    # Also activate breakout state machine
                    self.breakout_state = "ACTIVE"
                    self.breakout_bars_elapsed = 0
                    self.breakout_bar = {"breakout_dir": "bull", **last}
                    return {
                        "type": "breakout",
                        "direction": "bullish",
                        "time": last["time"],
                        "price": last["close"],
                        "pullback_depth": last_rng,
                        "pullback_bars": 1,
                        "regime_probability": regime_probability,
                        "pressure_score": pressure_score,
                    }

        if breakout == "bear_breakout" and env in ("structural_bear_trend", "trading_range"):
            last_rng = last["high"] - last["low"]
            if last_rng > 0:
                close_pos = (last["close"] - last["low"]) / last_rng
                if close_pos < 0.4 and pressure_score >= 3:
                    self.pending_breakout = {"direction": "bear_breakout", "bar": last}
                    self.breakout_state = "ACTIVE"
                    self.breakout_bars_elapsed = 0
                    self.breakout_bar = {"breakout_dir": "bear", **last}
                    return {
                        "type": "breakout",
                        "direction": "bearish",
                        "time": last["time"],
                        "price": last["close"],
                        "pullback_depth": last_rng,
                        "pullback_bars": 1,
                        "regime_probability": regime_probability,
                        "pressure_score": pressure_score,
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
            features["micro_double"] = 1.0 if signal.get("micro_double") else 0.0
            features["is_third_entry"] = 1.0 if signal.get("type") == "third_entry" else 0.0
            env = MarketEnvironmentClassifier.classify(mem, TrendAnalyzer.analyze(mem), PriceActionAnalyzer.trend_bar_info(mem))
            return features, atr, False, env

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

        # --- Dynamic Hard Filters based on Market Context (Version 3.1.0) ---
        # Instead of strict rigid filtering, we apply context.
        # Strong trends can break resistance. Ranges bounce off resistance.
        
        env = MarketEnvironmentClassifier.classify(mem, TrendAnalyzer.analyze(mem), PriceActionAnalyzer.trend_bar_info(mem))
        
        if env == "structural_bull_trend":
            hod_limit = 0.1
            pdh_limit = 0.1
            orh_limit = 0.1
        else:
            hod_limit = 0.5
            pdh_limit = 0.5
            orh_limit = 0.3

        if env == "structural_bear_trend":
            lod_limit = 0.1
            pdl_limit = 0.1
            orl_limit = 0.1
        else:
            lod_limit = 0.5
            pdl_limit = 0.5
            orl_limit = 0.3

        # HOD/LOD Hard Filter
        if signal.get("direction") == "bullish" and features.get("dist_to_hod_atr", 999) < hod_limit:
            return None
        if signal.get("direction") == "bearish" and features.get("dist_to_lod_atr", 999) < lod_limit:
            return None

        # Prior Day H/L Hard Filter
        if signal.get("direction") == "bullish" and features.get("dist_to_pdh_atr", 999) < pdh_limit:
            return None
        if signal.get("direction") == "bearish" and features.get("dist_to_pdl_atr", 999) < pdl_limit:
            return None

        # Opening Range Hard Filter
        if signal.get("direction") == "bullish" and features.get("dist_to_orh_atr", 999) < orh_limit:
            return None
        if signal.get("direction") == "bearish" and features.get("dist_to_orl_atr", 999) < orl_limit:
            return None

        # --- Extra ML features from signal metadata ---
        features["micro_double"] = 1.0 if signal.get("micro_double") else 0.0
        features["is_third_entry"] = 1.0 if signal.get("type") == "third_entry" else 0.0

        # Pass suboptimal tag if it was close to resistance but allowed by trend
        # This will command main engine to reduce risk position sizing.
        is_suboptimal = False
        if signal.get("direction") == "bullish":
            if min(features.get("dist_to_hod_atr", 999), features.get("dist_to_pdh_atr", 999)) < 0.5:
                is_suboptimal = True
        else:
            if min(features.get("dist_to_lod_atr", 999), features.get("dist_to_pdl_atr", 999)) < 0.5:
                is_suboptimal = True

        return features, atr, is_suboptimal, env
