"""AgentStatus — the lifecycle states an agent instance can be in."""

from enum import Enum, unique


@unique
class AgentStatus(Enum):
    """Lifecycle state of a single agent instance.

    Kept intentionally small and linear so any orchestrator can reason
    about valid transitions without importing agent-specific logic.
    """

    UNINITIALIZED = "uninitialized"   # constructed, not yet registered
    IDLE = "idle"                     # registered, awaiting work
    ASSIGNED = "assigned"             # a task has been handed to it
    RUNNING = "running"               # actively executing
    WAITING = "waiting"               # blocked on another agent/resource
    COMPLETED = "completed"           # finished its current task
    FAILED = "failed"                 # raised/returned an error
    DISABLED = "disabled"             # administratively turned off


# Transitions considered valid by convention. Orchestrators (e.g.
# AgentManager) may consult this to reject illegal status changes;
# it is data, not behavior, so it stays alongside the enum rather than
# inside AgentManager.
VALID_TRANSITIONS = {
    AgentStatus.UNINITIALIZED: {AgentStatus.IDLE, AgentStatus.DISABLED},
    AgentStatus.IDLE: {AgentStatus.ASSIGNED, AgentStatus.DISABLED},
    AgentStatus.ASSIGNED: {AgentStatus.RUNNING, AgentStatus.IDLE, AgentStatus.DISABLED},
    AgentStatus.RUNNING: {AgentStatus.WAITING, AgentStatus.COMPLETED, AgentStatus.FAILED},
    AgentStatus.WAITING: {AgentStatus.RUNNING, AgentStatus.FAILED},
    AgentStatus.COMPLETED: {AgentStatus.IDLE, AgentStatus.DISABLED},
    AgentStatus.FAILED: {AgentStatus.IDLE, AgentStatus.DISABLED},
    AgentStatus.DISABLED: {AgentStatus.IDLE},
}


def is_valid_transition(current: AgentStatus, target: AgentStatus) -> bool:
    """Pure function: is moving from `current` to `target` allowed?"""
    return target in VALID_TRANSITIONS.get(current, set())
