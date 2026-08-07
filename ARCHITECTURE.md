# Architecture Overview

This document outlines the evolved architecture of Lessan AI, transforming it into a production-grade AI Operating System while preserving backward compatibility with the existing codebase.

## Guiding Principles

The architecture adheres to the following principles:

- **Clean Architecture**: Separation of concerns with clear boundaries between layers.
- **SOLID Principles**: Ensuring modularity, scalability, and maintainability.
- **Dependency Injection**: Decoupling modules for better testability and flexibility.
- **Event-Driven Communication**: Modules communicate via an event bus to reduce tight coupling.
- **Plugin-Based Extension**: Support for future extensibility through plugins.
- **Interface-First Design**: Modules interact through well-defined interfaces.
- **Domain-Driven Organization**: Structuring the project around business domains.

## High-Level Architecture

The architecture is organized into the following top-level domains:

1. **Core**: Manages the application lifecycle, dependency injection, event bus, configuration, logging, and state management.
2. **UI**: Handles user interface components, workspaces, and plugins.
3. **Astral Core**: Represents the system's identity and visual state.
4. **Workspaces**: Provides domain-specific functionality for various user needs.
5. **Agents**: Implements a multi-agent framework for autonomous task execution.
6. **Engineering**: Supports the complete software engineering workflow.
7. **Memory**: Manages conversation, project, and agent memory.
8. **Models**: Routes and manages AI model providers.
9. **Voice**: Enables voice interaction capabilities.
10. **Vision**: Provides vision-related functionalities like OCR and image analysis.
11. **Automation**: Automates workflows and system interactions.
12. **Plugins**: Supports third-party integrations.
13. **Services**: Provides reusable services like notifications and telemetry.
14. **Security**: Ensures system security through permissions, encryption, and auditing.
15. **Storage**: Abstracts persistent storage mechanisms.
16. **API**: Exposes Lessan AI functionalities externally via REST and WebSocket APIs.
17. **Tests**: Contains unit, integration, and end-to-end tests.
18. **Documentation**: Hosts project documentation.

## Core Architecture

The **Core** module is the backbone of the system, providing essential services such as:

- **Dependency Injection**: Ensures loose coupling between modules.
- **Event Bus**: Facilitates communication between modules.
- **Scheduler**: Manages task scheduling.
- **Configuration**: Centralized configuration management.
- **Logging**: Structured logging for debugging and monitoring.
- **State Management**: Maintains global application state.

## Workspace Framework

The **Workspace Framework** allows for the creation of modular and extensible workspaces. Each workspace inherits from a `BaseWorkspace` and can be independently extended. Predefined workspaces include:

- Personal Workspace
- Engineering Workspace
- Cybersecurity Workspace
- Research Workspace
- Automation Workspace
- Settings Workspace

## Multi-Agent Framework

The **Multi-Agent Framework** provides reusable components for creating autonomous agents. Key components include:

- `BaseAgent`: Abstract base class for all agents.
- `AgentManager`: Manages agent lifecycle and communication.
- `AgentRegistry`: Registers and tracks agents.
- `AgentMemory`: Stores agent-specific memory.
- `AgentTask` and `AgentResult`: Define tasks and handle results.

Specialized agents include:

- Executive Agents (e.g., CEO, Product Manager)
- Engineering Agents (e.g., Frontend Engineer, Backend Engineer)
- Security Agents
- Research Agents
- Automation Agents

## Engineering Workflow

The **Engineering Workspace** supports the entire software engineering lifecycle, including:

1. Requirements Analysis
2. Project Planning
3. Architecture Design
4. Database Design
5. UI Design
6. Frontend Development
7. Backend Development
8. Testing
9. Security Review
10. Deployment
11. Monitoring
12. Documentation

Each stage is represented by reusable modules.

## Model Router

The **Model Router** manages AI model providers, supporting:

- Provider priority
- Fallback mechanisms
- Cost optimization
- Capability-based routing

Supported providers include Anthropic, OpenAI, Gemini, OpenRouter, OmniRouter, Ollama, and local models.

## Plugin System

The **Plugin System** enables third-party integrations through:

- `PluginManager`
- `PluginRegistry`
- `PluginLoader`
- `PluginAPI`

Future plugins may include GitHub, Docker, AWS, Azure, Firebase, PostgreSQL, Stripe, Slack, and Discord.

## Memory Architecture

The **Memory Module** includes:

- Conversation Memory
- Project Memory
- Agent Memory
- Shared Memory
- Knowledge Base (Vector Store Abstraction)

## Voice and Vision

The **Voice Module** supports speech recognition, text-to-speech, wake word detection, and streaming. The **Vision Module** provides OCR, image analysis, screen capture, and UI understanding.

## Automation

The **Automation Module** enables computer control, browser automation, terminal automation, file automation, and workflow automation.

## Security and Services

The **Security Module** ensures system integrity through permissions, encryption, sandboxing, and auditing. The **Services Module** provides reusable services like notifications, telemetry, and updates.

## API Layer

The **API Layer** exposes Lessan AI functionalities via REST and WebSocket APIs, with support for authentication.

## Tests and Documentation

The **Tests Module** includes unit, integration, and end-to-end tests. The **Documentation Module** provides detailed project documentation.

## Future Expansion

The architecture is designed for long-term evolution, supporting new features and integrations while maintaining backward compatibility.