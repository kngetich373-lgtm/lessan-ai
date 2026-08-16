# Lessan AI Repository Audit — 2026-08-16

## Scope

Audit performed against the GitHub repository because the original local development machine is unavailable. The audit uses the current `main` branch plus the latest development PR containing live model discovery. No secrets were read or committed.

## Baseline findings

### Architecture

The repository has the intended modular architecture around DI, Event Bus, state, scheduler, workflow, agents, workspaces, model routing and orchestration. The architecture documentation explicitly targets clean architecture, SOLID, dependency inversion, event-driven communication, plugins and interface-first design.

### Runtime integration gap

`main.py` still directly imports `google.genai`, reads `config/api_keys.json`, hard-codes a Gemini native-audio model and launches the legacy `LessanUI`. This means the new Model Router/System Orchestrator architecture is not yet the sole runtime path for the primary application.

### Provider lifecycle

The Model Router has a registry, health monitor, routing strategy and fallback strategy, but the original cloud base adapter contained `NotImplementedError` completion methods. Provider adapters therefore looked registered/configured without necessarily being executable.

The original cloud health check only tested whether an API key existed. Invalid credentials or unreachable endpoints could therefore be represented as healthy until a real request failed.

Persistent credentials in the legacy `config/api_keys.json` compatibility layer were not injected into provider instances; provider adapters primarily checked environment variables.

### Model discovery

The latest development PR adds live discovery for Gemini, Claude, OpenAI and OpenRouter while retaining static fallbacks. Discovery failures are intentionally non-fatal.

A centralized `ModelCapabilityRegistry` was missing from the repository despite the intended architecture calling for centralized capability metadata.

### Routing

The router already implements provider ranking, capability filtering, retries and fallback. A notable integration issue existed in `SystemOrchestrator`: it performed its own `is_available()` pre-check and replaced the router's actionable `No provider can serve this request` error with `No AI model route is available.` This duplicated routing policy in the orchestrator.

Streaming fallback also requires additional hardening because provider streaming errors can occur during iterator consumption rather than inside the initial route call.

### UI

There are two competing UI paths:

1. `lessan_ui.py` — a very large legacy/active monolithic PyQt6 UI with extensive drawing, telemetry, controls and interaction logic.
2. `ui/` — a newer modular UI architecture containing `MainWindow`, panel management, workspace/agent/plugin managers and UI state/event infrastructure.

The modular `ui/main_window.py` is currently incomplete: it references `SystemStatsPanel`, `ChatPanel`, `AstralCorePanel`, `PluginPanel`, `WorkspacePanel` and `AgentPanel` without importing or defining them, while `ui/components` currently contains only the base and panel-manager components. It cannot be treated as the stable application shell yet.

### Testing

The latest CI run for the live model-discovery work collected 164 tests and reported 163 passing and 1 failing. The failure was:

`tests/test_model_router_orchestrator_integration.py::test_router_reports_no_route_cleanly`

The test expected an error containing `No provider`, but the orchestrator's duplicate availability check produced `RuntimeError: No AI model route is available.`

## Work started on stabilization branch

Branch: `stabilize/provider-routing-ui`

The branch is intentionally based on the latest model-discovery development commit and is protected by a draft PR before any merge to `main`.

### Implemented

- `CredentialStore` with environment-first and persistent-config fallback resolution.
- DI wiring that injects resolved credentials into cloud provider adapters.
- OpenAI-compatible HTTP execution for OpenAI, OpenRouter, DeepSeek, Kimi and Qwen.
- Streaming transport for OpenAI-compatible providers.
- Reachability-aware health checking for OpenAI-compatible providers.
- Orchestrator change removing duplicated model availability policy.
- Central `ModelCapabilityRegistry` foundation.
- Provider lifecycle regression tests.
- Audit report documenting actual runtime gaps.

## Not yet claimed as complete

The following remain active work:

- full provider protocol implementations for Claude and Gemini completion/streaming;
- complete model capability registry integration into every routing decision;
- streaming fallback across multiple providers during iterator-time failures;
- provider refresh/recovery lifecycle and stale-provider cleanup;
- full configuration/settings UI integration;
- migration of `main.py` from direct Gemini/legacy UI execution to the orchestrated Model Router path;
- modular PyQt6 UI completion and Nielsen-based redesign;
- comprehensive startup/shutdown tests and end-to-end UI tests.

## Next engineering order

1. Make the stabilization CI green.
2. Complete provider protocol adapters and capability-registry integration.
3. Harden streaming fallback and health recovery.
4. Establish one authoritative application bootstrap path.
5. Complete modular PyQt6 shell without deleting legacy functionality.
6. Implement the Nielsen heuristic redesign incrementally.
7. Add settings/provider management UI.
8. Run full offline regression and Qt offscreen tests before considering merge.
