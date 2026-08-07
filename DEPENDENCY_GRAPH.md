# Dependency Graph

This document outlines the dependencies between the top-level domains in the Lessan AI architecture. The graph ensures modularity, scalability, and maintainability by adhering to Clean Architecture principles.

## Dependency Rules

1. **Core**: The foundational layer. All other modules depend on Core, but Core has no dependencies.
2. **UI**: Depends on Core and Astral Core for rendering and state management.
3. **Astral Core**: Depends on Core for state management and event handling.
4. **Workspaces**: Depends on Core, UI, and Agents for workspace functionality.
5. **Agents**: Depends on Core, Models, and Memory for agent lifecycle and task execution.
6. **Engineering**: Depends on Agents, Models, Automation, and Storage for the engineering workflow.
7. **Memory**: Depends on Core and Storage for memory persistence.
8. **Models**: Depends on Core and Services for model routing and management.
9. **Voice**: Depends on Core and Models for voice interaction.
10. **Vision**: Depends on Core and Models for vision capabilities.
11. **Automation**: Depends on Core, Agents, and Security for workflow automation.
12. **Plugins**: Depends on Core for plugin lifecycle management.
13. **Services**: Depends on Core for reusable utilities.
14. **Security**: Depends on Core for system protection.
15. **Storage**: Depends on Core for data persistence.
16. **API**: Depends on Core and Services for external communication.
17. **Tests**: Depends on all modules for comprehensive testing.
18. **Documentation**: No dependencies.

## Graph Representation

```
Core
├── UI
│   └── Astral Core
├── Workspaces
│   ├── UI
│   └── Agents
├── Agents
│   ├── Models
│   └── Memory
├── Engineering
│   ├── Agents
│   ├── Models
│   ├── Automation
│   └── Storage
├── Memory
│   └── Storage
├── Models
│   └── Services
├── Voice
│   └── Models
├── Vision
│   └── Models
├── Automation
│   ├── Agents
│   └── Security
├── Plugins
├── Services
├── Security
├── Storage
├── API
│   └── Services
├── Tests
│   ├── Core
│   ├── UI
│   ├── Astral Core
│   ├── Workspaces
│   ├── Agents
│   ├── Engineering
│   ├── Memory
│   ├── Models
│   ├── Voice
│   ├── Vision
│   ├── Automation
│   ├── Plugins
│   ├── Services
│   ├── Security
│   └── Storage
└── Documentation
```

## Key Insights

- **Core** is the only module with no dependencies, ensuring it remains the foundation of the architecture.
- **Tests** depend on all modules, ensuring comprehensive coverage.
- **Documentation** has no dependencies, making it independent of the system's functionality.

## Future Considerations

- Ensure new modules follow the dependency rules to maintain modularity.
- Regularly review dependencies to avoid tight coupling.
- Use Dependency Injection to manage dependencies dynamically.