"""Streaming Service — manages streaming responses across gateways."""

from typing import Any, Dict, List, Optional


class StreamingService:
    """Coordinates streaming responses from gateways.

    The Streaming Service maintains active stream sessions and provides
    a unified interface for the Routing Engine to consume streamed chunks
    without knowing the underlying gateway.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Any] = {}

    def register_session(self, session_id: str, stream: Any) -> None:
        self._sessions[session_id] = stream

    def unregister_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def active_sessions(self) -> List[str]:
        return list(self._sessions.keys())
