"""
Agent Communication API.

A minimal pub/sub-style message bus so agents (e.g. CEO Agent
coordinating others) can exchange structured messages without any
agent holding a direct reference to another agent's internals. This
keeps agents loosely coupled — CEO Agent depends on
IAgentCommunicationBus, not on concrete agent classes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, unique
from typing import Callable, Optional, Protocol, runtime_checkable
from uuid import uuid4


@unique
class MessageType(Enum):
    """Categories of inter-agent messages. Kept small; richer semantics
    (e.g. task-specific payload shapes) belong in `AgentMessage.payload`,
    not in new enum members, to avoid this enum growing unbounded."""

    REQUEST = "request"          # ask another agent to do something
    RESPONSE = "response"        # reply to a REQUEST
    STATUS_UPDATE = "status_update"
    BROADCAST = "broadcast"      # informational, no reply expected
    ERROR = "error"


@dataclass(frozen=True)
class AgentMessage:
    """A single message passed between agents on the bus."""

    sender: str
    message_type: MessageType
    payload: dict = field(default_factory=dict)
    recipient: Optional[str] = None  # None => broadcast to all subscribers
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


MessageHandler = Callable[[AgentMessage], None]


@runtime_checkable
class IAgentCommunicationBus(Protocol):
    """Messaging contract. An agent (or AgentManager) subscribes by
    name and publishes messages; the bus handles routing."""

    def subscribe(self, agent_name: str, handler: MessageHandler) -> None: ...

    def unsubscribe(self, agent_name: str) -> None: ...

    def publish(self, message: AgentMessage) -> None: ...


class InProcessCommunicationBus:
    """Default, dependency-free implementation of IAgentCommunicationBus
    for a single-process deployment. A distributed deployment can
    implement the same interface over e.g. a message queue without
    touching any agent code.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, MessageHandler] = {}
        self._history: list[AgentMessage] = []

    def subscribe(self, agent_name: str, handler: MessageHandler) -> None:
        self._handlers[agent_name] = handler

    def unsubscribe(self, agent_name: str) -> None:
        self._handlers.pop(agent_name, None)

    def publish(self, message: AgentMessage) -> None:
        self._history.append(message)
        if message.recipient is not None:
            handler = self._handlers.get(message.recipient)
            if handler:
                handler(message)
            return
        # Broadcast: everyone except the sender.
        for name, handler in self._handlers.items():
            if name != message.sender:
                handler(message)

    def history(self) -> list[AgentMessage]:
        """Read-only view of every message published so far — useful
        for debugging/auditing agent coordination."""
        return list(self._history)
