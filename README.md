# Lessan AI

> A modular AI engineering assistant for building, automating, and operating software systems.

Lessan AI is designed around a simple idea: **an AI assistant should do more than chat**. It should understand a task, plan work, use tools, coordinate specialized agents, remember useful context, and execute workflows with explicit safety boundaries.

## Why Lessan AI?

Lessan brings together:

- **Multi-provider model routing** — connect and route across OpenAI-compatible and major cloud/local providers.
- **Agent framework** — specialized agents coordinated through a common runtime.
- **Tool use** — controlled access to shell, files, web, automation, and application capabilities.
- **Memory** — conversation and persistent context designed for useful continuity.
- **Workflow automation** — turn multi-step requests into repeatable engineering workflows.
- **Plugin architecture** — extend the system without tightly coupling core components.
- **Observability** — expose agent, task, model, and system activity so automation remains understandable.

## Architecture

Lessan is organized around modular boundaries rather than one large assistant class:

```text
User Request
     │
     ▼
System Orchestrator
     │
     ├── Model Router ──► Cloud / Local Providers
     ├── Agent Manager ─► Specialized Agents
     ├── Workflow Engine
     ├── Tool Registry ─► Governed Tools
     ├── Memory ────────► Short + Long Term Context
     ├── Plugin System
     └── Event Bus / State Manager
```

Core responsibilities are separated so individual subsystems can evolve independently.

## Core capabilities

### Agents

Specialized agents can handle different classes of work while sharing common lifecycle, status, memory, and tool interfaces.

### Model routing

Lessan is intended to work across multiple providers rather than depending on a single model vendor. Provider health, capability, availability, and fallback behavior can be handled by the routing layer.

### Tools and security

Tool access is deliberately separated from model access. Dangerous operations should pass through explicit permission and policy boundaries instead of granting an LLM unrestricted system access.

### Memory

Conversation context and persistent memory allow the assistant to retain useful information without treating every previous message as permanent context.

### Workflows

The workflow layer supports repeatable multi-step operations and provides a foundation for autonomous engineering loops: plan → execute → observe → recover → verify.

## Project structure

```text
lessan-ai/
├── core/             Core runtime, DI, events, state, and shared interfaces
├── agents/            Base and specialized agents
├── workflows/        Workflow execution and orchestration
├── tools/             Tool registry and tool implementations
├── plugins/           Plugin discovery, registry, and lifecycle
├── memory/            Conversation and persistent memory
├── gateway/           Multi-provider model gateway/routing
├── ui/                Desktop user interface and workspaces
├── config/             Application configuration
├── tests/              Automated tests
└── docs/               Architecture and engineering documentation
```

> Directory names may evolve as the architecture is consolidated; treat the source tree and tests as the implementation contract.

## Getting started

### Requirements

- Python 3.11+
- Git
- A supported desktop environment for the GUI
- API credentials for whichever model providers you choose to enable

### Setup

```bash
git clone https://github.com/kngetich373-lgtm/lessan-ai.git
cd lessan-ai

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure provider credentials using the project's environment/configuration mechanism. **Never commit API keys or other secrets.**

Then launch the application using the repository's current entrypoint/start script.

## Development

Run the test suite before and after significant architectural changes:

```bash
pytest
```

When adding a subsystem:

1. Define the interface/boundary.
2. Implement the smallest useful version.
3. Add tests.
4. Wire it through dependency injection or the appropriate registry.
5. Add observability and failure handling.
6. Update documentation.

## Engineering principles

- **Modular first** — keep responsibilities isolated.
- **Interfaces over coupling** — depend on contracts where practical.
- **Observable automation** — autonomous behavior should be inspectable.
- **Safe by default** — tool permissions must remain explicit.
- **Test before expansion** — architecture should be protected by automated tests.
- **Provider agnostic** — avoid locking the core runtime to one model vendor.
- **Useful UX** — complexity belongs behind a clear interface.

## Security

Treat model output as untrusted input. Do not give an AI model unrestricted shell, filesystem, credential, or network privileges. Use least-privilege tools, explicit confirmation for high-risk actions, audit logging, and environment-based secret management.

## Project status

Lessan AI is an actively evolving engineering project. Architecture and APIs may change while the platform is consolidated into a stable AI engineering runtime.

## License

See `LICENSE` for the repository's license terms.

---

<div align="center">

**Lessan AI — understand · plan · build · verify**

</div>
