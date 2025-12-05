# Services Architecture

Clean separation: domain services for presentation, infrastructure for core services.

## Structure

```
services/
├── __init__.py              # Public API exports
├── community/               # Community domain (presentation layer)
│   ├── __init__.py
│   └── dashboard_service.py # Community dashboard data aggregation
├── user/                    # User domain (presentation layer)
│   ├── __init__.py
│   └── dashboard_service.py # User-specific dashboard data
└── infrastructure/          # Core services & infrastructure
    ├── __init__.py
    ├── model_service.py        # Community model configuration management (MongoDB)
    ├── simulation_engine.py    # Core simulation engine
    ├── simulation_utils.py     # Simulation utilities (denormalization, behavioral modifiers)
    ├── control_service.py      # External control interfaces (DR, member management)
    ├── background_service.py   # Background simulation caching service
    ├── system_notice_service.py # System notifications & alerts
    └── output_handlers.py      # Generic output handlers (REST, MQTT, Kafka, File)
```

## Usage

### Recommended (Clean Imports)
```python
from app.services import (
    # Domain services (presentation)
    CommunityDashboardService,
    UserDashboardService,
    # Infrastructure (core services)
    CommunityModelService,
    CommunitySimulationEngine,
    CommunityControlService,
    get_background_service,
    SystemNoticeService
)
```

### Domain-Specific Imports
```python
# Domain (presentation layer)
from app.services.community import CommunityDashboardService
from app.services.user import UserDashboardService

# Infrastructure (core services)
from app.services.infrastructure import (
    CommunityModelService,
    CommunitySimulationEngine,
    get_background_service
)
```

## Service Dependencies

```
Domain Services (Presentation Layer):
  community/dashboard_service → simulation_engine, model_service, background_service
  user/dashboard_service → simulation_engine, model_service, background_service

Infrastructure (Core Services):
  model_service → MongoDB
  simulation_engine → model_service, simulation_utils, output_handlers
  simulation_utils → Domain utilities (denormalization, behavioral modifiers)
  control_service → model_service, simulation_engine
  background_service → model_service, simulation_engine
  system_notice_service → MongoDB
  output_handlers → Generic output mechanisms (REST, MQTT, Kafka, File)
```

## Design Principles

1. **Clean Architecture**: Domain folders (`community/`, `user/`) contain only presentation services (dashboards)
2. **Infrastructure Layer**: Core services, engines, and technical utilities live in `infrastructure/`
3. **Single Responsibility**: Each service has a clear, focused purpose
4. **Dependency Injection**: Services accept dependencies through constructors
5. **Clean Imports**: Public API exposed through `__init__.py` files
6. **Separation of Concerns**: Presentation (domain), core logic (infrastructure), and utilities are clearly separated

