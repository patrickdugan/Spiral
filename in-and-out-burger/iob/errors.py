class Refusal(Exception):
    """An order the desk will not serve. `reason` is a stable code; `detail` is for people."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail
