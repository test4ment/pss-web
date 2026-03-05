"""
db/base.py — Abstract base class for all storage backends.
"""

from abc import ABC, abstractmethod


class BaseStorage(ABC):

    @abstractmethod
    def init(self) -> None:
        """Create tables / collections. Must be idempotent."""

    @abstractmethod
    def save_departures(self, records: list[dict]) -> tuple[int, int]:
        """Insert records. Returns (inserted, skipped_duplicates)."""

    @abstractmethod
    def get_departures(self, sql_where: str = "", params: list = None) -> list[dict]:
        """Fetch departure records with optional filtering."""

    @abstractmethod
    def search_departures(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search in description_raw."""

    @abstractmethod
    def stats(self) -> dict:
        """Return aggregated statistics dict."""
