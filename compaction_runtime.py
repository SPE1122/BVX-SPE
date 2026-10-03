"""Request-local time budgets for optional loading-plan searches."""

from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import logging
import time


logger = logging.getLogger(__name__)


@dataclass
class CompactionBudget:
    per_platform_seconds: float = 20.0
    total_seconds: float = 60.0
    overall_deadline: float | None = None
    platform_deadlines: dict = field(default_factory=dict)
    reported_platforms: set = field(default_factory=set)

    def deadline(self, platform):
        now = time.monotonic()
        if self.overall_deadline is None:
            self.overall_deadline = now + self.total_seconds
        key = str(platform)
        if key not in self.platform_deadlines:
            self.platform_deadlines[key] = now + self.per_platform_seconds
        return min(self.overall_deadline, self.platform_deadlines[key])

    def expired(self, platform):
        expired = time.monotonic() >= self.deadline(platform)
        if expired and str(platform) not in self.reported_platforms:
            self.reported_platforms.add(str(platform))
            logger.warning(
                "Verdichtungsbudget erreicht (%s): weitere Zusatzsuche entfällt; "
                "nur vollständig geprüfte Anordnungen bleiben erhalten.", platform,
            )
        return expired


_budget = ContextVar("loading_compaction_budget", default=None)


def compaction_budget():
    budget = _budget.get()
    if budget is None:
        raise RuntimeError("Compaction searches require a request-local budget")
    return budget


def with_compaction_budget(function):
    """Nested stages and repeated candidates share one budget, not process state."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _budget.get() is not None:
            return function(*args, **kwargs)
        budget = CompactionBudget()
        token = _budget.set(budget)
        try:
            result = function(*args, **kwargs)
            # Keep the notice with saved plans without changing return signatures.
            frames = result if isinstance(result, tuple) else (result,)
            for frame in frames:
                if hasattr(frame, "attrs"):
                    frame.attrs["Verdichtungsbudget_erreicht"] = sorted(budget.reported_platforms)
            return result
        finally:
            _budget.reset(token)
    return wrapped