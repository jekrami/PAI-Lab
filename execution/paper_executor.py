class PaperExecutor:

    def __init__(self):
        self.open_position = None

    def execute_trade(self, direction, entry_price, stop, target):
        self.open_position = {
            "direction": direction,
            "entry": entry_price,
            "stop": stop,
            "target": target
        }

        print(f"[PAPER] Opened {direction} @ {entry_price}")

    def check_exit(self, candle):
        if not self.open_position:
            return None

        direction = self.open_position["direction"]

        if direction == "long":
            if candle["high"] >= self.open_position["target"]:
                print("[PAPER] Target Hit")
                self.open_position = None
                return 1

            if candle["low"] <= self.open_position["stop"]:
                print("[PAPER] Stop Hit")
                self.open_position = None
                return 0

        return None
