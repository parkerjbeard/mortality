from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Force anyio-powered tests to use asyncio, which matches the runtime implementation."""
    return "asyncio"
