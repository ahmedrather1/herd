"""Rebalance planning (Epic C): resolved intent → concrete orders.

C-1 (`Planner`) produces the ordered order set; constraint-solving (C-2) and current-vs-
target display (C-3) build on it.
"""

from __future__ import annotations

from .allocation import AllocationReport, AllocationRow, compute_allocation
from .constraints import ConstraintSet, ConstraintSolver, PlanResult, parse_constraints
from .models import Plan, PlannedOrder
from .planner import Planner
from .validation import OrderProblem, OrderValidator, ValidationResult

__all__ = [
    "Planner",
    "Plan",
    "PlannedOrder",
    "compute_allocation",
    "AllocationReport",
    "AllocationRow",
    "OrderValidator",
    "ValidationResult",
    "OrderProblem",
    "ConstraintSolver",
    "ConstraintSet",
    "PlanResult",
    "parse_constraints",
]
