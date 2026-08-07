"""Extended capability system for task-based provider routing.

Defines fine-grained capabilities beyond basic ones (streaming, vision, etc.)
to enable intelligent task-based routing.
"""

from typing import Dict, List, Set

# Extended task-based capabilities
CAPABILITY_GENERAL_CHAT = "general_chat"
CAPABILITY_REASONING = "reasoning"
CAPABILITY_LONG_CONTEXT = "long_context"

# Programming languages
CAPABILITY_PYTHON = "python"
CAPABILITY_JAVASCRIPT = "javascript"
CAPABILITY_TYPESCRIPT = "typescript"
CAPABILITY_JAVA = "java"
CAPABILITY_CPP = "cpp"
CAPABILITY_CSHARP = "csharp"
CAPABILITY_GO = "go"
CAPABILITY_RUST = "rust"
CAPABILITY_PHP = "php"
CAPABILITY_RUBY = "ruby"

# Development domains
CAPABILITY_FRONTEND_DEV = "frontend_development"
CAPABILITY_BACKEND_DEV = "backend_development"
CAPABILITY_FULLSTACK_DEV = "fullstack_development"
CAPABILITY_MOBILE_DEV = "mobile_development"
CAPABILITY_DEVOPS = "devops"
CAPABILITY_DATABASE = "database"

# Frameworks & technologies
CAPABILITY_REACT = "react"
CAPABILITY_VUE = "vue"
CAPABILITY_ANGULAR = "angular"
CAPABILITY_FLUTTER = "flutter"
CAPABILITY_REACT_NATIVE = "react_native"
CAPABILITY_DJANGO = "django"
CAPABILITY_FLASK = "flask"
CAPABILITY_NODEJS = "nodejs"
CAPABILITY_SPRING = "spring"

# Specialized domains
CAPABILITY_SECURITY = "security"
CAPABILITY_DOCUMENTATION = "documentation"
CAPABILITY_DATA_ANALYSIS = "data_analysis"
CAPABILITY_MACHINE_LEARNING = "machine_learning"
CAPABILITY_WEB_SCRAPING = "web_scraping"
CAPABILITY_TESTING = "testing"
CAPABILITY_DEBUGGING = "debugging"
CAPABILITY_CODE_REVIEW = "code_review"
CAPABILITY_ARCHITECTURE = "architecture"
CAPABILITY_PERFORMANCE = "performance_optimization"


# All known capabilities
ALL_CAPABILITIES: Set[str] = {
    "text", "streaming", "vision", "tool_calling", "embeddings",
    "audio", "image_generation", "multilingual",
    CAPABILITY_GENERAL_CHAT, CAPABILITY_REASONING, CAPABILITY_LONG_CONTEXT,
    CAPABILITY_PYTHON, CAPABILITY_JAVASCRIPT, CAPABILITY_TYPESCRIPT,
    CAPABILITY_JAVA, CAPABILITY_CPP, CAPABILITY_CSHARP, CAPABILITY_GO,
    CAPABILITY_RUST, CAPABILITY_PHP, CAPABILITY_RUBY,
    CAPABILITY_FRONTEND_DEV, CAPABILITY_BACKEND_DEV, CAPABILITY_FULLSTACK_DEV,
    CAPABILITY_MOBILE_DEV, CAPABILITY_DEVOPS, CAPABILITY_DATABASE,
    CAPABILITY_REACT, CAPABILITY_VUE, CAPABILITY_ANGULAR,
    CAPABILITY_FLUTTER, CAPABILITY_REACT_NATIVE,
    CAPABILITY_DJANGO, CAPABILITY_FLASK, CAPABILITY_NODEJS, CAPABILITY_SPRING,
    CAPABILITY_SECURITY, CAPABILITY_DOCUMENTATION, CAPABILITY_DATA_ANALYSIS,
    CAPABILITY_MACHINE_LEARNING, CAPABILITY_WEB_SCRAPING,
    CAPABILITY_TESTING, CAPABILITY_DEBUGGING, CAPABILITY_CODE_REVIEW,
    CAPABILITY_ARCHITECTURE, CAPABILITY_PERFORMANCE,
}


CAPABILITY_GROUPS: Dict[str, List[str]] = {
    "web_frontend": [
        CAPABILITY_FRONTEND_DEV, CAPABILITY_JAVASCRIPT, CAPABILITY_TYPESCRIPT,
        CAPABILITY_REACT, CAPABILITY_VUE, CAPABILITY_ANGULAR,
    ],
    "web_backend": [
        CAPABILITY_BACKEND_DEV, CAPABILITY_PYTHON, CAPABILITY_NODEJS,
        CAPABILITY_JAVA, CAPABILITY_DATABASE, CAPABILITY_DJANGO,
        CAPABILITY_FLASK, CAPABILITY_SPRING,
    ],
    "mobile": [CAPABILITY_MOBILE_DEV, CAPABILITY_FLUTTER, CAPABILITY_REACT_NATIVE],
    "systems_programming": [CAPABILITY_CPP, CAPABILITY_RUST, CAPABILITY_GO, CAPABILITY_PERFORMANCE],
    "data_science": [CAPABILITY_PYTHON, CAPABILITY_DATA_ANALYSIS, CAPABILITY_MACHINE_LEARNING],
    "security": [CAPABILITY_SECURITY, CAPABILITY_CODE_REVIEW, CAPABILITY_DEBUGGING],
}


def expand_capability_groups(capabilities: List[str]) -> Set[str]:
    """Expand capability group names into individual capabilities."""
    expanded: Set[str] = set()
    for cap in capabilities:
        if cap in CAPABILITY_GROUPS:
            expanded.update(CAPABILITY_GROUPS[cap])
        else:
            expanded.add(cap)
    return expanded


def validate_capabilities(capabilities: List[str]) -> List[str]:
    """Validate and normalize capability names."""
    valid = []
    expanded = expand_capability_groups(capabilities)
    for cap in expanded:
        normalized = cap.lower().strip().replace("-", "_")
        if normalized in ALL_CAPABILITIES:
            valid.append(normalized)
    return valid
