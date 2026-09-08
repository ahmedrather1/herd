"""Proposal & confirmation loop (Epic D): assemble a confirmable proposal (D-1)."""

from __future__ import annotations

from .models import Proposal, ProposalOutcome, ProposalStatus
from .service import ProposalService

__all__ = ["ProposalService", "Proposal", "ProposalOutcome", "ProposalStatus"]
