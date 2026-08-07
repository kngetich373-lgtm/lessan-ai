"""AgentMessenger — inter-agent communication and mailbox."""

import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.event_bus import event_bus
from core.logging import get_logger

logger = get_logger("agents.messenger")


@dataclass
class AgentMessage:
    """A message between agents."""

    sender: str
    recipient: str
    content: Any
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None


class AgentMessenger:
    """Mailbox-based messenger for agents.

    Each recipient has a mailbox. Synchronous request/response and
    fire-and-forget sends are supported. Messages are also published on
    the event bus for observability.
    """

    def __init__(self) -> None:
        self._mailboxes: Dict[str, queue.Queue] = {}
        self._lock = threading.RLock()

    def _mailbox(self, recipient: str) -> queue.Queue:
        with self._lock:
            if recipient not in self._mailboxes:
                self._mailboxes[recipient] = queue.Queue()
            return self._mailboxes[recipient]

    def send(self, sender: str, recipient: str, content: Any, reply_to: Optional[str] = None) -> AgentMessage:
        """Fire-and-forget send to a recipient's mailbox."""
        msg = AgentMessage(sender=sender, recipient=recipient, content=content, reply_to=reply_to)
        self._mailbox(recipient).put(msg)
        event_bus.emit("agent.message", {
            "sender": sender, "recipient": recipient, "content": content,
            "message_id": msg.message_id,
        })
        logger.debug(f"Message {msg.message_id}: {sender} → {recipient}")
        return msg

    def receive(self, recipient: str, timeout: float = 0.1) -> Optional[AgentMessage]:
        try:
            return self._mailbox(recipient).get(timeout=timeout)
        except queue.Empty:
            return None

    def request(self, sender: str, recipient: str, content: Any, timeout: float = 10.0) -> Any:
        """Send a message and wait synchronously for a reply."""
        msg = self.send(sender, recipient, content)
        deadline = datetime.now().timestamp() + timeout
        while datetime.now().timestamp() < deadline:
            response = self.receive(sender, timeout=0.5)
            if response and response.reply_to == msg.message_id:
                return response.content
        raise TimeoutError(f"No reply from '{recipient}' within {timeout}s")

    def reply(self, original: AgentMessage, content: Any) -> AgentMessage:
        """Reply to an original message."""
        return self.send(
            sender=original.recipient or "",
            recipient=original.sender,
            content=content,
            reply_to=original.message_id,
        )

    def clear_mailbox(self, recipient: str) -> int:
        """Clear and discard all messages in a recipient's mailbox."""
        mailbox = self._mailbox(recipient)
        count = 0
        while not mailbox.empty():
            try:
                mailbox.get_nowait()
                count += 1
            except queue.Empty:
                break
        return count

    def pending_count(self, recipient: str) -> int:
        return self._mailbox(recipient).qsize()


# Global messenger
agent_messenger = AgentMessenger()