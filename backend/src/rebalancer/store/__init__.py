"""Local persistence layer (A-3, D23/D49): SQLite via SQLModel, normalized audit schema.

Public surface: the ``AuditStore`` write/read API, the engine/session helpers, and the
table models. Money is stored as exact TEXT via ``DecimalString`` (D45).
"""

from __future__ import annotations

from .audit import AuditStore, ProposedLeg
from .db import (
    DEFAULT_DB_PATH,
    DecimalString,
    create_db_and_tables,
    get_engine,
    make_engine,
    session_scope,
)
from .models import (
    AppSession,
    Conversation,
    Intent,
    LlmCall,
    OrderExecution,
    Proposal,
    ProposedOrder,
    Request,
    RequestStatus,
)

__all__ = [
    "AuditStore",
    "ProposedLeg",
    "DEFAULT_DB_PATH",
    "DecimalString",
    "create_db_and_tables",
    "get_engine",
    "make_engine",
    "session_scope",
    "AppSession",
    "Conversation",
    "Intent",
    "LlmCall",
    "OrderExecution",
    "Proposal",
    "ProposedOrder",
    "Request",
    "RequestStatus",
]
