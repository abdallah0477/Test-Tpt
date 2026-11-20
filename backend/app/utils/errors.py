"""ApiError: a feature raises it to return an AD-14 error envelope with its own code.

Example: raise ApiError(422, "invalid_url", "only http and https URLs can be inspected")
"""

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details
