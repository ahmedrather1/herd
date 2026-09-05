"""Test configuration.

Presence of this file puts ``tests/`` on ``sys.path`` (pytest prepend import mode) so
``from fakes.fake_alpaca import ...`` resolves regardless of invocation directory.

It also points the persistence layer (A-3/D49) at a throwaway temp DB via
``REBALANCER_DB_URL`` before the app is imported, so exercising the app lifespan in tests
(which auto-creates the DB) never writes into the repo's ``backend/data/`` directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "REBALANCER_DB_URL",
    f"sqlite:///{Path(tempfile.gettempdir()) / 'rebalancer_test.db'}",
)
