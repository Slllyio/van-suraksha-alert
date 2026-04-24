"""Data-access layer for the v3 portal.

Thin repository classes that wrap the file-I/O helpers currently living
in ``serve.py``. Route handlers can migrate to the repository interface
incrementally; existing handlers continue to call ``_load_*`` functions
directly until converted. The interfaces below document the intended
boundaries for a future refactor (e.g., FastAPI migration, test-only
mock backends).

Pattern reference: ``Repository Pattern`` in the backend-patterns skill.
"""
from .v17_repository import V17Repository
from .division_repository import DivisionRepository
from .boundaries_repository import BoundariesRepository

__all__ = ["V17Repository", "DivisionRepository", "BoundariesRepository"]
