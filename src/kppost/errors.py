class KppostError(Exception):
    """Base error for expected application failures."""


class ValidationError(KppostError):
    """Raised when a batch is invalid."""

    def __init__(self, messages: list[str] | str):
        self.messages = [messages] if isinstance(messages, str) else messages
        super().__init__("\n".join(self.messages))


class WordPressError(KppostError):
    """Raised for WordPress API failures."""

    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)

