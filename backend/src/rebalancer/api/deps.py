"""FastAPI dependency providers wiring the real services (D24, D46).

Endpoints depend on these; tests override them with fakes. The services are synchronous
(D46) and endpoints are declared ``def`` so FastAPI runs them in a threadpool.
"""

from __future__ import annotations

from ..alpaca import get_alpaca_client
from ..config import get_settings
from ..execution import ExecutionService
from ..proposal import ProposalService
from ..store import AuditStore, get_engine


def get_store() -> AuditStore:
    return AuditStore(get_engine())


def get_proposal_service() -> ProposalService:
    return ProposalService.from_settings(get_settings(), get_alpaca_client(), store=get_store())


def get_execution_service() -> ExecutionService:
    return ExecutionService(get_alpaca_client(), get_store())
