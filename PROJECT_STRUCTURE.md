# Project Structure

The following directory structure reflects the evolution of Lessan AI into a production‑grade AI Operating System while preserving backward compatibility with the existing codebase.

```
lessan-ai/
├── core/                     # Core infrastructure
│   ├── di/                   # Dependency Injection containers
│   ├── event_bus/            # Event bus implementation
│   ├── scheduler/            # Task scheduler
│   ├── configuration/        # Global configuration management
│   ├── logging/              # Structured logging framework
│   └── state/                # Global state management
│
├── ui/                       # User interface components
│   ├── main_window.py        # Main application window
│   ├── components/           # Reusable UI components
│   │   ├── base.py
│   │   └── panel_manager.py
│   ├── plugins/              # UI plugin system
│   │   ├── plugin_base.py
│   │   └── plugin_manager.py
│   ├── workspaces/           # Workspace frameworks
│   │   ├── engineering_workspace.py
│   │   ├── personal_workspace.py
│   │   ├── cybersecurity_workspace.py
│   │   ├── research_workspace.py
│   │   ├── automation_workspace.py
│   │   └── settings_workspace.py
│   └── theme.py              # Theme and styling definitions
│
├── astral_core/              # System identity and visual layer
│   ├── rendering/            # Rendering engine
│   ├── animations/           # Animation system
│   ├── particle_system/      # Particle effects
│   ├── agent_orbits/         # Agent visual representation
│   └── visual_states/        # System state visualizations
│
├── workspaces/               # Domain‑specific workspace modules
│   ├── personal/
│   ├── engineering/
│   ├── cybersecurity/
│   ├── research/
│   ├── automation/
│   └── settings/
│
├── agents/                   # Agent framework
│   ├── base_agent.py
│   ├── agent_manager.py
│   ├── agent_registry.py
│   ├── communication/        # Communication protocols
│   ├── memory/               # Agent memory abstractions
│   ├── task/                 # Task definitions and execution
│   └── results/              # Agent result handling
│
├── engineering/              # Engineering workspace modules
│   ├── requirements_analysis/
│   ├── project_planning/
│   ├── architecture_design/
│   ├── database_design/
│   ├── ui_design/
│   ├── frontend/
│   ├── backend/
│   ├── testing/
│   ├── security_review/
│   ├── deployment/
│   ├── monitoring/
│   └── documentation/
│
├── memory/                   # Memory architecture
│   ├── conversation_memory.py
│   ├── project_memory.py
│   ├── agent_memory.py
│   ├── shared_memory.py
│   └── knowledge_base/       # Vector store abstraction
│
├── models/                   # Model routing and selection
│   ├── model_router.py
│   ├── providers/
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   ├── gemini.py
│   │   ├── openrouter.py
│   │   ├── omnirouter.py
│   │   ├── ollama.py
│   │   └── local.py
│   └── routing_strategies/
│
├── voice/                    # Voice interaction layer
│   ├── speech_recognition.py
│   ├── text_to_speech.py
│   ├── wake_word.py
│   ├── streaming.py
│   └── integration/
│
├── vision/                   # Vision capabilities
│   ├── ocr.py
│   ├── image_analysis.py
│   ├── screen_processor.py
│   └── camera/
│
├── automation/               # Automation layer
│   ├── computer_control.py
│   ├── browser_automation.py
│   ├── terminal_automation.py
│   ├── file_automation.py
│   └── workflow_automation.py
│
├── plugins/                  # Plugin system
│   ├── plugin_manager.py
│   ├── plugin_registry.py
│   ├── plugin_loader.py
│   └── plugin_api.py
│
├── services/                 # Reusable services
│   ├── notification_service.py
│   ├── metrics_service.py
│   ├── authentication.py
│   ├── telemetry.py
│   └── update_service.py
│
├── security/                 # Security modules
│   ├── permissions.py
│   ├── secrets.py
│   ├── encryption.py
│   ├── sandbox.py
│   └── audit.py
│
├── storage/                  # Persistent storage abstractions
│   ├── file_storage.py
│   ├── database_storage.py
│   └── cache/
│
├── api/                      # API layer
│   ├── rest.py
│   ├── websocket.py
│   └── authentication.py
│
├── tests/                    # Test suites
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── documentation/            # Project documentation
    ├── architecture.md
    ├── module_responsibilities.md
    ├── dependency_graph.md
    └── development_roadmap.md
```

*All existing files and modules remain untouched; new directories are added to host the expanded architecture.*