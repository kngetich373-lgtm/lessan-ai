"""Capability Matcher — intelligent task analysis and capability inference."""

import re
from typing import List, Set

from core.model_router.capabilities import (
    CAPABILITY_PYTHON, CAPABILITY_JAVASCRIPT, CAPABILITY_TYPESCRIPT,
    CAPABILITY_JAVA, CAPABILITY_CPP, CAPABILITY_REACT, CAPABILITY_FRONTEND_DEV,
    CAPABILITY_BACKEND_DEV, CAPABILITY_SECURITY, CAPABILITY_DATABASE,
    CAPABILITY_REASONING, CAPABILITY_GENERAL_CHAT,
)

# Simplified pattern matching for key capabilities
PATTERNS = {
    CAPABILITY_PYTHON: [r"\bpython\b", r"\.py\b", r"\bdjango\b", r"\bflask\b"],
    CAPABILITY_JAVASCRIPT: [r"\bjavascript\b", r"\bjs\b", r"\.js\b", r"\bnode\b"],
    CAPABILITY_TYPESCRIPT: [r"\btypescript\b", r"\bts\b", r"\.tsx?\b"],
    CAPABILITY_JAVA: [r"\bjava\b", r"\.java\b", r"\bspring\b"],
    CAPABILITY_CPP: [r"\bc\+\+\b", r"\bcpp\b", r"\.cpp\b"],
    CAPABILITY_REACT: [r"\breact\b", r"\bjsx\b"],
    CAPABILITY_FRONTEND_DEV: [r"\bfrontend\b", r"\bui\b", r"\bhtml\b", r"\bcss\b"],
    CAPABILITY_BACKEND_DEV: [r"\bbackend\b", r"\bapi\b", r"\bserver\b"],
    CAPABILITY_SECURITY: [r"\bsecurity\b", r"\bvulnerability\b", r"\bhack\b"],
    CAPABILITY_DATABASE: [r"\bdatabase\b", r"\bsql\b", r"\bmongo\b"],
    CAPABILITY_REASONING: [r"\banalyze\b", r"\breason\b", r"\bexplain\b"],
}


class CapabilityMatcher:
    """Analyzes task descriptions to infer required capabilities."""
    
    def __init__(self) -> None:
        self._patterns = {
            cap: [re.compile(p, re.IGNORECASE) for p in patterns]
            for cap, patterns in PATTERNS.items()
        }
    
    def infer_capabilities(self, task: str) -> List[str]:
        """Infer required capabilities from a task description."""
        if not task or not task.strip():
            return [CAPABILITY_GENERAL_CHAT]
        
        matches: Set[str] = set()
        for capability, patterns in self._patterns.items():
            for pattern in patterns:
                if pattern.search(task):
                    matches.add(capability)
                    break
        
        if not matches:
            matches.add(CAPABILITY_GENERAL_CHAT)
        
        return sorted(matches)
    
    def match_score(self, required: List[str], available: List[str]) -> float:
        """Calculate how well available capabilities match required ones."""
        if not required:
            return 1.0
        required_set = set(cap.lower() for cap in required)
        available_set = set(cap.lower() for cap in available)
        matched = required_set & available_set
        return len(matched) / len(required_set)


_matcher = CapabilityMatcher()


def infer_capabilities(task: str) -> List[str]:
    """Convenience function to infer capabilities using the global matcher."""
    return _matcher.infer_capabilities(task)


def match_score(required: List[str], available: List[str]) -> float:
    """Convenience function to calculate match score using the global matcher."""
    return _matcher.match_score(required, available)
