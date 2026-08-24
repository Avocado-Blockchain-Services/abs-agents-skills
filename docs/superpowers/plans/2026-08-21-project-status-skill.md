# perseaai-agents-status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un desarrollador pueda preguntar desde la terminal si su integración con la plataforma está funcionando y cómo va su proyecto, y obtener una respuesta que distinga *roto* de *apagado* de *todavía sin datos*.

**Architecture:** Tres tools MCP de lectura en `persea-agents-api` que envuelven servicios que ya existen (`StatsService`, `ProjectIssueService`, `DebuggerRunService`) sin modificarlos, más una skill nueva en `abs-agents-skills` que lleva toda la lógica de diagnóstico en markdown. Los datos viajan por MCP; el criterio vive en el SKILL.md, de modo que ajustarlo no requiere desplegar la API.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, `mcp.server.mcpserver.MCPServer`, pytest, ruff, mypy, Docker Compose. Del lado de la skill: markdown formato agentskills.io.

**Spec:** `docs/superpowers/specs/2026-08-21-project-status-skill-design.md` (en este mismo repo)

## Global Constraints

- **Dos repos, dos ramas.** `persea-agents-api` → rama `feat/mcp-project-status` desde `development` (Tareas 1–3). `abs-agents-skills` → rama `feat/project-status-skill`, **ya creada desde `development` y con el spec commiteado** (Tareas 4–5).
- **Autor de los commits:** `Cristhian Arboleda <casboleda@avocadoblock.com>`. **Sin líneas `Co-Authored-By`.**
- **Nada corre en el host.** Todo comando de Python va por Docker: `docker compose exec api pytest ...`, `docker compose exec api ruff ...`, `docker compose exec api mypy ...`. Levantar con `docker compose up -d --build` desde `persea-agents-api/`.
- **Lectura pura.** Ninguna de las tres tools escribe. Ningún cambio a `StatsService`, `ProjectIssueService` ni `DebuggerRunService`.
- **Módulo apagado devuelve `null`, nunca `0`.** La clave siempre está presente; el valor es `null`. Todo el diagnóstico de la skill depende de esta distinción.
- **Tenencia uniforme.** Un proyecto que el caller no puede ver responde exactamente igual que uno inexistente: `ValueError("Project not found")`. Nunca "Access denied" — nombrar la diferencia deja sondear qué ids existen.
- **Versiones:** `.claude-plugin/plugin.json` `0.3.0` → `0.4.0`. La skill nueva arranca en `metadata.version: "0.1.0"`. `perseaai-agents-setup` conserva `0.3.4` sin tocar.
- **Los dos validadores del repo de skills tienen que pasar:** `python3 scripts/validate_skill.py <ruta>` y `python3 scripts/validate_tool_references.py <ruta>`.

---

### Task 1: Resolución de proyecto con tenencia

El helper que las tres tools comparten. Se hace primero y solo, porque es donde vive la única decisión de seguridad de todo el trabajo.

**Files:**
- Create: `src/mcp/tools/project_status.py`
- Test: `tests/unit/mcp/test_project_status_tools.py`

**Interfaces:**
- Consumes: `src.mcp.get_mcp_uow`, `src.mcp.auth.require_mcp_auth`, `uow.project_repository.get_with_services`, `uow.membership_repository.get_by_user_and_org`
- Produces: `_resolve_project_scope(uow: UnitOfWork, project_id: UUID) -> Project` — devuelve el proyecto **con sus services cargados**, o lanza `ValueError`. Las Tareas 2 y 3 la llaman y leen `project.organization_id` y `project.services`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/unit/mcp/test_project_status_tools.py`:

```python
"""Las tools de estado leen datos que ya existen; lo único que deciden por su
cuenta es a quién le contestan. Eso es lo que se prueba primero."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp.auth import McpUserInfo, current_mcp_user
from src.mcp.tools.project_status import _resolve_project_scope
from src.orm.models.project import Project
from src.orm.repositories.membership_repository import MembershipRepository
from src.orm.repositories.project_repository import ProjectRepository
from src.orm.unit_of_work import UnitOfWork

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def make_user() -> McpUserInfo:
    return McpUserInfo(
        user_id=USER_ID,
        email="dev@example.com",
        name="Dev",
        auth0_sub="auth0|dev",
    )


def make_project(organization_id=ORG_ID):
    project = MagicMock(spec=Project)
    project.id = PROJECT_ID
    project.name = "persea"
    project.organization_id = organization_id
    project.services = []
    return project


def make_uow(project, membership):
    """Specced, para que un repositorio renombrado falle ruidosamente."""
    uow = MagicMock(spec=UnitOfWork)
    uow.project_repository = MagicMock(spec=ProjectRepository)
    uow.project_repository.get_with_services = AsyncMock(return_value=project)
    uow.membership_repository = MagicMock(spec=MembershipRepository)
    uow.membership_repository.get_by_user_and_org = AsyncMock(return_value=membership)
    return uow


class TestResolveProjectScope:
    def setup_method(self) -> None:
        current_mcp_user.set(None)

    async def test_sin_caller_autenticado_no_resuelve_nada(self) -> None:
        current_mcp_user.set(None)
        uow = make_uow(make_project(), MagicMock())
        with pytest.raises(ValueError, match="Authentication required"):
            await _resolve_project_scope(uow, PROJECT_ID)

    async def test_un_proyecto_inexistente_es_project_not_found(self) -> None:
        current_mcp_user.set(make_user())
        uow = make_uow(None, MagicMock())
        with pytest.raises(ValueError, match="Project not found"):
            await _resolve_project_scope(uow, PROJECT_ID)

    async def test_un_proyecto_ajeno_responde_igual_que_uno_inexistente(self) -> None:
        """Nombrar la diferencia ('Access denied') dejaría sondear qué ids
        existen: el mensaje tiene que ser indistinguible."""
        current_mcp_user.set(make_user())
        uow = make_uow(make_project(organization_id=OTHER_ORG_ID), None)
        with pytest.raises(ValueError, match="Project not found"):
            await _resolve_project_scope(uow, PROJECT_ID)

    async def test_un_proyecto_propio_vuelve_con_sus_services(self) -> None:
        current_mcp_user.set(make_user())
        project = make_project()
        uow = make_uow(project, MagicMock())
        resolved = await _resolve_project_scope(uow, PROJECT_ID)
        assert resolved is project
        uow.project_repository.get_with_services.assert_awaited_once_with(PROJECT_ID)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
docker compose exec api pytest tests/unit/mcp/test_project_status_tools.py -v
```

Esperado: FAIL con `ModuleNotFoundError: No module named 'src.mcp.tools.project_status'`.

- [ ] **Step 3: Escribir la implementación mínima**

Crear `src/mcp/tools/project_status.py`:

```python
"""Tools MCP de solo lectura sobre el estado del pipeline de un proyecto.

Los contadores ya existían: `StatsService` los calcula para
`GET /v1/projects/{id}/stats`. Lo que no existía era una vía para que un agente
en una terminal los leyera — el servidor lite solo exponía onboarding. Estas
tres agregan esa vía y nada más: sin escrituras y sin métricas nuevas.
"""

from uuid import UUID

from src.mcp.auth import require_mcp_auth
from src.orm.models.project import Project
from src.orm.unit_of_work import UnitOfWork

_PROJECT_NOT_FOUND = "Project not found"


async def _resolve_project_scope(uow: UnitOfWork, project_id: UUID) -> Project:
    """El proyecto, probado como perteneciente a una organización del caller.

    Un proyecto que el caller no puede ver responde exactamente igual que uno
    inexistente. Nombrar la diferencia dejaría sondear qué ids son reales.

    Devuelve el proyecto con `services` ya cargados: las tres tools los usan y
    una segunda consulta por lo mismo sería trabajo repetido dentro de la misma
    unidad de trabajo.
    """
    user = require_mcp_auth()
    project = await uow.project_repository.get_with_services(project_id)
    if project is None:
        raise ValueError(_PROJECT_NOT_FOUND)
    membership = await uow.membership_repository.get_by_user_and_org(
        user.user_id, project.organization_id
    )
    if membership is None:
        raise ValueError(_PROJECT_NOT_FOUND)
    return project
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
docker compose exec api pytest tests/unit/mcp/test_project_status_tools.py -v
```

Esperado: 4 passed.

- [ ] **Step 5: Lint y tipos**

```bash
docker compose exec api ruff check src/mcp/tools/project_status.py tests/unit/mcp/test_project_status_tools.py
docker compose exec api ruff format --check src/mcp/tools/project_status.py tests/unit/mcp/test_project_status_tools.py
docker compose exec api mypy src/mcp/tools/project_status.py
```

Esperado: los tres en verde.

- [ ] **Step 6: Commit**

```bash
git add src/mcp/tools/project_status.py tests/unit/mcp/test_project_status_tools.py
git -c user.name="Cristhian Arboleda" -c user.email="casboleda@avocadoblock.com" \
  commit -m "feat: resolucion de proyecto con tenencia para las tools de estado"
```

---

### Task 2: `get_project_status` — la tool que responde el 90%

**Files:**
- Modify: `src/mcp/tools/project_status.py` (agregar `_service_row` y `get_project_status_tool`)
- Modify: `src/mcp/lite.py` (registrar la tool)
- Modify: `src/mcp/full.py` (registrar la tool)
- Test: `tests/unit/mcp/test_project_status_tools.py` (agregar clase)

**Interfaces:**
- Consumes: `_resolve_project_scope` (Tarea 1), `StatsService.get_project_stats(project_id, organization_id)`, `src.core.firestore.get_firestore_client`, `src.core.redis.get_redis_client`
- Produces: `get_project_status_tool(project_id: str) -> dict` con las claves `project_id`, `name`, `stats`, `module_flags`, `services`. `services[]` trae `service_id`, `repo_full_name`, `branch`, `service_type`, `status`, `infra_status`, `last_activity_at` (ISO-8601 o `None`), `pr_url`. La Tarea 4 escribe la skill contra exactamente estas claves.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/unit/mcp/test_project_status_tools.py`:

```python
from datetime import UTC, datetime
from unittest.mock import patch

from src.orm.models.service import Service
from src.schemas.stats import (
    ClassifierStats,
    LogsStats,
    ProjectStatsResponse,
    SummaryStats,
)

SERVICE_ID = uuid.uuid4()
LAST_ACTIVITY = datetime(2026, 8, 20, 10, 30, tzinfo=UTC)


class _FakeUowContext:
    """`get_mcp_uow()` devuelve un context manager async; el doble tiene que
    serlo también."""

    def __init__(self, uow):
        self._uow = uow

    async def __aenter__(self):
        return self._uow

    async def __aexit__(self, *exc_info):
        return False


def make_service():
    service = MagicMock(spec=Service)
    service.id = SERVICE_ID
    service.repo_full_name = "Avocado-Blockchain-Services/todo-api"
    service.branch = "main"
    service.service_type = "BACKEND"
    service.status = "ACTIVE"
    service.infra_status = "ACTIVE"
    service.last_activity_at = LAST_ACTIVITY
    service.pr_url = "https://github.com/org/todo-api/pull/7"
    return service


def stats_with_classifier_off() -> ProjectStatsResponse:
    """Lo que devuelve `StatsService` cuando el modulo esta apagado: el objeto
    entero en None, no un contador en cero."""
    return ProjectStatsResponse(
        logs=LogsStats(errors_received=12, issues_grouped=4),
        classifier=None,
        debugger=None,
        results=None,
        summary=SummaryStats(awaiting_review=2),
        module_flags={"logs_enabled": True, "classifier_enabled": False, "debugger_enabled": False},
        agents=[],
    )


class TestGetProjectStatus:
    def setup_method(self) -> None:
        current_mcp_user.set(make_user())

    async def _call(self, project, stats):
        from src.mcp.tools import project_status as module

        uow = make_uow(project, MagicMock())
        stats_service = MagicMock()
        stats_service.get_project_stats = AsyncMock(return_value=stats)
        with (
            patch.object(module, "get_mcp_uow", return_value=_FakeUowContext(uow)),
            patch.object(module, "get_firestore_client", AsyncMock(return_value=None)),
            patch.object(module, "get_redis_client", AsyncMock(return_value=None)),
            patch.object(module, "StatsService", return_value=stats_service),
        ):
            return await module.get_project_status_tool(str(PROJECT_ID))

    async def test_expone_last_activity_at_por_service(self) -> None:
        """Es el dato genuinamente nuevo: separa 'nunca llego un log' de
        'llegaban y se cortaron', y ninguna tool MCP lo exponia."""
        project = make_project()
        project.services = [make_service()]
        result = await self._call(project, ProjectStatsResponse())
        assert result["services"] == [
            {
                "service_id": str(SERVICE_ID),
                "repo_full_name": "Avocado-Blockchain-Services/todo-api",
                "branch": "main",
                "service_type": "BACKEND",
                "status": "ACTIVE",
                "infra_status": "ACTIVE",
                "last_activity_at": "2026-08-20T10:30:00Z",
                "pr_url": "https://github.com/org/todo-api/pull/7",
            }
        ]

    async def test_un_service_sin_actividad_dice_none_no_se_omite(self) -> None:
        project = make_project()
        service = make_service()
        service.last_activity_at = None
        service.status = "NO_DATA"
        project.services = [service]
        result = await self._call(project, ProjectStatsResponse())
        assert result["services"][0]["last_activity_at"] is None
        assert result["services"][0]["status"] == "NO_DATA"

    async def test_un_modulo_apagado_llega_como_null_y_no_como_cero(self) -> None:
        """La distincion de la que depende todo el diagnostico de la skill:
        `classifier: null` es apagado, `classifier: {classified: 0}` es
        encendido y sin clasificar nada."""
        project = make_project()
        project.services = [make_service()]
        result = await self._call(project, stats_with_classifier_off())
        assert "classifier" in result["stats"]
        assert result["stats"]["classifier"] is None
        assert result["stats"]["logs"] == {"errors_received": 12, "issues_grouped": 4}

    async def test_los_module_flags_quedan_en_el_nivel_superior(self) -> None:
        project = make_project()
        project.services = [make_service()]
        result = await self._call(project, stats_with_classifier_off())
        assert result["module_flags"]["classifier_enabled"] is False

    async def test_las_stats_se_piden_para_la_organizacion_del_proyecto(self) -> None:
        """Pasar otra organizacion haria que StatsService responda 404 sobre un
        proyecto que el caller si puede ver."""
        from src.mcp.tools import project_status as module

        project = make_project()
        project.services = []
        uow = make_uow(project, MagicMock())
        stats_service = MagicMock()
        stats_service.get_project_stats = AsyncMock(return_value=ProjectStatsResponse())
        with (
            patch.object(module, "get_mcp_uow", return_value=_FakeUowContext(uow)),
            patch.object(module, "get_firestore_client", AsyncMock(return_value=None)),
            patch.object(module, "get_redis_client", AsyncMock(return_value=None)),
            patch.object(module, "StatsService", return_value=stats_service),
        ):
            await module.get_project_status_tool(str(PROJECT_ID))
        stats_service.get_project_stats.assert_awaited_once_with(PROJECT_ID, ORG_ID)
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
docker compose exec api pytest tests/unit/mcp/test_project_status_tools.py::TestGetProjectStatus -v
```

Esperado: FAIL con `AttributeError: ... has no attribute 'get_project_status_tool'`.

- [ ] **Step 3: Escribir la implementación**

Agregar los imports que faltan al principio de `src/mcp/tools/project_status.py`:

```python
from datetime import datetime

from src.core.firestore import get_firestore_client
from src.core.redis import get_redis_client
from src.mcp import get_mcp_uow
from src.orm.models.service import Service
from src.services.stats_service import StatsService
```

`last_activity_at` es `DateTime(timezone=True)` en el modelo, asi que siempre
llega con tz y `_iso` no tiene que adivinar nada.

Y al final del archivo:

```python
def _iso(moment: datetime | None) -> str | None:
    """ISO-8601 con `Z`, como serializa pydantic.

    La respuesta de una tool MCP se serializa a JSON, que no tiene tipo fecha.
    El bloque `stats` de la misma respuesta lo produce pydantic, que emite
    `2026-08-20T10:30:00Z`, mientras que `datetime.isoformat()` emite
    `...+00:00`. Dos formatos para lo mismo dentro de un solo payload es
    exactamente la clase de detalle que despues rompe una comparacion.
    """
    if moment is None:
        return None
    return moment.isoformat().replace("+00:00", "Z")


def _service_row(service: Service) -> dict:
    """Un service tal como lo necesita el diagnostico."""
    return {
        "service_id": str(service.id),
        "repo_full_name": service.repo_full_name,
        "branch": service.branch,
        "service_type": service.service_type,
        "status": service.status,
        "infra_status": service.infra_status,
        "last_activity_at": _iso(service.last_activity_at),
        "pr_url": service.pr_url,
    }


async def get_project_status_tool(project_id: str) -> dict:
    """Estado completo del pipeline de un proyecto en una sola llamada."""
    resolved_id = UUID(project_id)
    async with get_mcp_uow() as uow:
        project = await _resolve_project_scope(uow, resolved_id)
        stats_service = StatsService(
            uow,
            await get_firestore_client(),
            await get_redis_client(),
        )
        stats = await stats_service.get_project_stats(resolved_id, project.organization_id)
        return {
            "project_id": str(project.id),
            "name": project.name,
            # `mode="json"` y sin `exclude_none`: un modulo apagado tiene que
            # llegar como `null` con su clave presente. Omitirla dejaria al
            # consumidor sin poder distinguir "apagado" de "el servidor no
            # reporta esto", que es justo la distincion sobre la que se apoya
            # el diagnostico del lado de la skill.
            "stats": stats.model_dump(mode="json"),
            # Duplicado a proposito desde `stats`: es el primer dato que hay que
            # mirar para leer cualquier contador en cero, y enterrarlo un nivel
            # mas abajo invita a saltearlo.
            "module_flags": stats.module_flags,
            "services": [_service_row(service) for service in project.services],
        }
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
docker compose exec api pytest tests/unit/mcp/test_project_status_tools.py -v
```

Esperado: 9 passed.

- [ ] **Step 5: Registrar la tool en el servidor lite**

En `src/mcp/lite.py`, agregar al bloque de imports:

```python
from src.mcp.tools.project_status import get_project_status_tool
```

Y registrar la tool **justo antes** de `@mcp_lite.prompt()` / `async def logcore_setup`:

```python
@mcp_lite.tool()
async def get_project_status(project_id: str) -> dict:
    """Get the current pipeline state of a project: logs, classifier, debugger.

    Returns the counters, the module flags, and every service with its
    `status`, `infra_status` and `last_activity_at`.

    A module that is switched off comes back as `null` (not `0`): `classifier:
    null` means the module is disabled, while `classifier: {"classified": 0}`
    means it is running and has classified nothing. Read `module_flags` before
    reading any counter as a failure.

    Args:
        project_id: UUID of the project (from list_projects)
    """
    return await get_project_status_tool(project_id)
```

- [ ] **Step 6: Registrar la misma tool en el servidor full**

En `src/mcp/full.py`, con el mismo import y el mismo cuerpo, registrado sobre `mcp_full` en vez de `mcp_lite`, respetando el orden en que ese archivo declara las demás tools (después de `register_pr`).

- [ ] **Step 7: Verificar que la suite completa sigue verde**

```bash
docker compose exec api pytest tests/ -q
docker compose exec api ruff check src/mcp tests/unit/mcp
docker compose exec api mypy src/mcp
```

Esperado: todo en verde, sin regresiones.

- [ ] **Step 8: Commit**

```bash
git add src/mcp/tools/project_status.py src/mcp/lite.py src/mcp/full.py tests/unit/mcp/test_project_status_tools.py
git -c user.name="Cristhian Arboleda" -c user.email="casboleda@avocadoblock.com" \
  commit -m "feat: tool MCP get_project_status con stats, flags y actividad por service"
```

---

### Task 3: Las dos tools de drill-down

`get_project_issue` y `list_debugger_runs` van juntas: son envoltorios delgados del mismo tamaño y un revisor las acepta o rechaza por el mismo motivo.

**Files:**
- Modify: `src/mcp/tools/project_status.py`
- Modify: `src/mcp/lite.py`
- Modify: `src/mcp/full.py`
- Test: `tests/unit/mcp/test_project_status_tools.py`

**Interfaces:**
- Consumes: `_resolve_project_scope` (Tarea 1), `ProjectIssueService.get_for_project(project_id, organization_id, fingerprint)`, `DebuggerRunService.list_for_project(project_id, organization_id, *, status_filter, limit, offset)`
- Produces: `get_project_issue_tool(project_id: str, fingerprint: str) -> dict` (volcado JSON de `ProjectIssueDetail`) y `list_debugger_runs_tool(project_id: str, status: str | None = None, limit: int = 20) -> list[dict]` (volcado JSON de `DebuggerRunSummary`).

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/unit/mcp/test_project_status_tools.py`:

```python
from fastapi import HTTPException

from src.schemas.debugger_run import DebuggerRunSummary
from src.schemas.project_issue import ProjectIssueDetail


class TestDrillDownTools:
    def setup_method(self) -> None:
        current_mcp_user.set(make_user())

    async def test_el_detalle_de_un_issue_vuelve_serializado(self) -> None:
        from src.mcp.tools import project_status as module

        project = make_project()
        uow = make_uow(project, MagicMock())
        issue_service = MagicMock()
        issue_service.get_for_project = AsyncMock(
            return_value=ProjectIssueDetail(
                fingerprint="abc123",
                code="E-1",
                title="TypeError en /todos",
                complexity="simple",
                outcome="resolved",
                first_seen=LAST_ACTIVITY,
            )
        )
        with (
            patch.object(module, "get_mcp_uow", return_value=_FakeUowContext(uow)),
            patch.object(module, "get_firestore_client", AsyncMock(return_value=None)),
            patch.object(module, "get_redis_client", AsyncMock(return_value=None)),
            patch.object(module, "ProjectIssueService", return_value=issue_service),
        ):
            result = await module.get_project_issue_tool(str(PROJECT_ID), "abc123")

        assert result["fingerprint"] == "abc123"
        assert result["complexity"] == "simple"
        assert result["first_seen"] == "2026-08-20T10:30:00Z"
        issue_service.get_for_project.assert_awaited_once_with(PROJECT_ID, ORG_ID, "abc123")

    async def test_un_issue_inexistente_se_traduce_a_valueerror(self) -> None:
        """Los servicios levantan HTTPException, que del lado MCP no significa
        nada: el cliente veria un 500 en vez del motivo."""
        from src.mcp.tools import project_status as module

        uow = make_uow(make_project(), MagicMock())
        issue_service = MagicMock()
        issue_service.get_for_project = AsyncMock(
            side_effect=HTTPException(status_code=404, detail="Issue not found")
        )
        with (
            patch.object(module, "get_mcp_uow", return_value=_FakeUowContext(uow)),
            patch.object(module, "get_firestore_client", AsyncMock(return_value=None)),
            patch.object(module, "get_redis_client", AsyncMock(return_value=None)),
            patch.object(module, "ProjectIssueService", return_value=issue_service),
        ):
            with pytest.raises(ValueError, match="Issue not found"):
                await module.get_project_issue_tool(str(PROJECT_ID), "nope")

    async def test_los_runs_se_listan_con_el_filtro_de_status(self) -> None:
        from src.mcp.tools import project_status as module

        uow = make_uow(make_project(), MagicMock())
        run_service = MagicMock()
        run_service.list_for_project = AsyncMock(
            return_value=[
                DebuggerRunSummary(
                    id=uuid.uuid4(),
                    run_id="run-1",
                    fingerprint="abc123",
                    service_name="todo-api",
                    repo_full_name="org/todo-api",
                    env="dev",
                    status="failed",
                    termination_reason="max_cycles",
                    cost_usd=0.42,
                    cycles_used=8,
                )
            ]
        )
        with (
            patch.object(module, "get_mcp_uow", return_value=_FakeUowContext(uow)),
            patch.object(module, "DebuggerRunService", return_value=run_service),
        ):
            result = await module.list_debugger_runs_tool(str(PROJECT_ID), status="failed")

        assert result[0]["termination_reason"] == "max_cycles"
        assert result[0]["cost_usd"] == 0.42
        run_service.list_for_project.assert_awaited_once_with(
            PROJECT_ID, ORG_ID, status_filter="failed", limit=20, offset=0
        )

    async def test_un_limit_desmedido_se_recorta_al_maximo(self) -> None:
        """`DebuggerRunService` no acota nada por su cuenta: el endpoint HTTP lo
        hace con `Query(le=MAX_PAGE_SIZE)`, y por MCP no hay Query."""
        # 5000 -> 100, el tope declarado en `_MAX_RUNS`.
        from src.mcp.tools import project_status as module

        uow = make_uow(make_project(), MagicMock())
        run_service = MagicMock()
        run_service.list_for_project = AsyncMock(return_value=[])
        with (
            patch.object(module, "get_mcp_uow", return_value=_FakeUowContext(uow)),
            patch.object(module, "DebuggerRunService", return_value=run_service),
        ):
            await module.list_debugger_runs_tool(str(PROJECT_ID), limit=5000)

        run_service.list_for_project.assert_awaited_once_with(
            PROJECT_ID, ORG_ID, status_filter=None, limit=100, offset=0
        )
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

```bash
docker compose exec api pytest tests/unit/mcp/test_project_status_tools.py::TestDrillDownTools -v
```

Esperado: FAIL con `AttributeError: ... has no attribute 'get_project_issue_tool'`.

- [ ] **Step 3: Escribir la implementación**

Agregar a los imports de `src/mcp/tools/project_status.py`:

```python
from fastapi import HTTPException

from src.services.debugger_run_service import DebuggerRunService
from src.services.project_issue_service import ProjectIssueService
```

Y la constante del tope, junto a `_PROJECT_NOT_FOUND`:

```python
# El mismo tope que `Query(le=MAX_PAGE_SIZE)` impone en
# `src/api/v1/endpoints/debugger_runs.py`. Declarado aca en vez de importado
# de alli: un modulo MCP no deberia depender de la capa HTTP, y el tope de
# issues (`project_issue_service.MAX_PAGE_SIZE`) vale lo mismo hoy por
# casualidad, no por contrato.
_MAX_RUNS = 100
```

Y al final del archivo:

```python
async def get_project_issue_tool(project_id: str, fingerprint: str) -> dict:
    """El detalle de un issue: veredicto, PRs y cada run con sus pasos."""
    resolved_id = UUID(project_id)
    async with get_mcp_uow() as uow:
        project = await _resolve_project_scope(uow, resolved_id)
        issue_service = ProjectIssueService(
            uow,
            await get_firestore_client(),
            await get_redis_client(),
        )
        try:
            detail = await issue_service.get_for_project(
                resolved_id, project.organization_id, fingerprint
            )
        except HTTPException as exc:
            # Los servicios hablan HTTP porque nacieron detras de un endpoint.
            # Una HTTPException que escapa de una tool MCP llega al cliente como
            # un error de transporte sin motivo legible; el detalle es
            # exactamente lo que el agente necesita leer.
            raise ValueError(str(exc.detail)) from exc
        return detail.model_dump(mode="json")


async def list_debugger_runs_tool(
    project_id: str,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Los runs del debugger de un proyecto, del mas reciente al mas viejo."""
    resolved_id = UUID(project_id)
    async with get_mcp_uow() as uow:
        project = await _resolve_project_scope(uow, resolved_id)
        try:
            runs = await DebuggerRunService(uow).list_for_project(
                resolved_id,
                project.organization_id,
                status_filter=status,
                # El servicio no acota: el endpoint HTTP lo hace con
                # `Query(ge=1, le=MAX_PAGE_SIZE)`, y por MCP no hay Query. Sin
                # esto, un `limit` inventado por un modelo se traduce en una
                # consulta sin techo.
                limit=max(1, min(limit, _MAX_RUNS)),
                offset=0,
            )
        except HTTPException as exc:
            raise ValueError(str(exc.detail)) from exc
        return [run.model_dump(mode="json") for run in runs]
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

```bash
docker compose exec api pytest tests/unit/mcp/test_project_status_tools.py -v
```

Esperado: 13 passed.

- [ ] **Step 5: Registrar ambas tools en lite y full**

En `src/mcp/lite.py` y `src/mcp/full.py`, importar `get_project_issue_tool` y `list_debugger_runs_tool` desde `src.mcp.tools.project_status` y registrarlas junto a `get_project_status`:

```python
@mcp_lite.tool()
async def get_project_issue(project_id: str, fingerprint: str) -> dict:
    """Get one issue's full history: complexity verdict, outcome, PRs, runs.

    Use after `get_project_status` when the user asks why a specific error is
    still open.

    Args:
        project_id: UUID of the project (from list_projects)
        fingerprint: The issue fingerprint
    """
    return await get_project_issue_tool(project_id, fingerprint)


@mcp_lite.tool()
async def list_debugger_runs(
    project_id: str,
    status: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List the project's debugger runs, most recent first.

    Each run carries `status`, `termination_reason`, `cost_usd`, `cycles_used`
    and `pr_url`. Use after `get_project_status` when the debugger's counters
    need explaining.

    Args:
        project_id: UUID of the project (from list_projects)
        status: Optional status filter (e.g. 'failed', 'completed')
        limit: How many runs to return (capped at 100)
    """
    return await list_debugger_runs_tool(project_id, status, limit)
```

- [ ] **Step 6: Suite completa, lint y tipos**

```bash
docker compose exec api pytest tests/ -q
docker compose exec api ruff check src/mcp tests/unit/mcp
docker compose exec api ruff format --check src/mcp tests/unit/mcp
docker compose exec api mypy src/mcp
```

Esperado: todo en verde.

- [ ] **Step 7: Commit y PR**

```bash
git add src/mcp/tools/project_status.py src/mcp/lite.py src/mcp/full.py tests/unit/mcp/test_project_status_tools.py
git -c user.name="Cristhian Arboleda" -c user.email="casboleda@avocadoblock.com" \
  commit -m "feat: tools MCP de drill-down sobre issues y runs del debugger"
git push -u origin feat/mcp-project-status
gh pr create --base development \
  --title "feat: tools MCP de lectura del estado de un proyecto" \
  --body "Tres tools de solo lectura sobre el MCP lite/full: \`get_project_status\`, \`get_project_issue\` y \`list_debugger_runs\`. Envuelven \`StatsService\`, \`ProjectIssueService\` y \`DebuggerRunService\` sin modificarlos. Habilitan la skill \`perseaai-agents-status\` en abs-agents-skills.

Spec: https://github.com/Avocado-Blockchain-Services/abs-agents-skills/blob/development/docs/superpowers/specs/2026-08-21-project-status-skill-design.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 8: Verificación real (bloquea la Tarea 4)**

Mergear a `development`, desplegar a dev, y en una sesión con el MCP `perseaai-agents-dev` conectado llamar `get_project_status` sobre un proyecto que **ya tenga issues y runs**. Confirmar a ojo que `services[].last_activity_at` viene poblado y que los contadores coinciden con lo que muestra la web app. Las tools no se dan por buenas hasta ver datos verdaderos.

---

### Task 4: El SKILL.md

Cambia de repo: `abs-agents-skills`, rama `feat/project-status-skill` (ya existe, ya tiene el spec commiteado).

**Files:**
- Create: `skills/perseaai-agents-status/SKILL.md`

**Interfaces:**
- Consumes: las tools de las Tareas 2 y 3 (`get_project_status`, `get_project_issue`, `list_debugger_runs`) más `list_projects`, que ya existe.
- Produces: la skill instalable. La Tarea 5 la empaqueta.

- [ ] **Step 1: Escribir el frontmatter y los Prerequisites**

Crear `skills/perseaai-agents-status/SKILL.md`. El `name` **tiene que ser idéntico al nombre de la carpeta** (`validate_skill.py` lo verifica) y el `description` no puede usar ni una palabra del vocabulario de onboarding (`connect`, `integrate`, `register`, `set up`), o compite con `perseaai-agents-setup` por el mismo trigger:

```markdown
---
name: perseaai-agents-status
description: >-
  Use when the user wants to check whether a project's logcore integration is
  actually working after setup, or wants the current state of a project on the
  Persea AI agents platform — logs arriving, issues grouped, classifier
  verdicts, debugger runs, PRs awaiting review. Requires the platform MCP
  server to be connected.
license: Apache-2.0
metadata:
  author: Avocado Blockchain Services
  version: "0.1.0"
---

# Persea AI Agents Platform — Project Status

Answer two questions: *is the integration working?* and *how is the project
doing?* Which one gets answered is decided from the data, not by asking.

## Prerequisites

This skill drives tools served by the Persea AI agents platform MCP server:
`list_projects`, `get_project_status`, `get_project_issue`, and
`list_debugger_runs`.

If these tools are not available in the session, the MCP server is not
connected. Stop and point the user to the installation instructions in this
plugin's README (https://github.com/Avocado-Blockchain-Services/abs-agents-skills)
before continuing.

This skill never writes. It cannot retry a run, close an issue, or toggle a
module. When the fix is a setup step, hand back to `perseaai-agents-setup`.
```

- [ ] **Step 2: Escribir la Fase 0 y la bifurcación**

Continuar el archivo. Cuidado con el orden de la condición: `stats.logs` puede ser `null`, así que se comprueba el objeto antes que el contador.

```markdown
## Phase 0: Identify the project

1. Call `list_projects`.
2. Read the local remote with `git remote -v` and match it against each
   service's `repo_full_name`.
3. Exactly one match: continue with that project. Zero or several: ask the
   user which project they mean. Do not guess.

## Choosing the phase

Call `get_project_status` with the project id. Then decide, without asking:

- any service with `status: "NO_DATA"`, **or** `stats.logs` is `null`, **or**
  `stats.logs.errors_received == 0` → **Phase 1**
- otherwise → **Phase 2**

Read `stats.logs` for existence before reading its counter. The object is
`null` when the logs module is off, and reading the counter first breaks the
skill on exactly the project that has the least data.

Phase 1 is not "something is broken". It can end at "all good, no errors
yet" — see row 6.
```

- [ ] **Step 3: Escribir la tabla de diagnóstico de la Fase 1**

Las celdas de acción de las filas 2, 3, 4 y 7 mencionan tools de onboarding. Escribirlas como **derivación** a `perseaai-agents-setup`, nunca con el idiom ``call `get_infra_setup``` — `validate_tool_references.py` exigiría declararlas en Prerequisites, y una skill que declara tools que no usa es la deriva que ese validador existe para atrapar.

```markdown
## Phase 1: Diagnose

Walk the table in order and **stop at the first link that fails**. Reporting
three problems when the second is a consequence of the first is how a skill
becomes noise.

| # | Condition | Reading | What to tell the user |
|---|---|---|---|
| 1 | `pr_url` is null | The integration was never completed | Hand back to `perseaai-agents-setup` |
| 2 | `infra_status: "NOT_CONFIGURED"` (backends only) | The Cloud Logging sink is missing | The sink was never created — resume `perseaai-agents-setup` |
| 3 | `infra_status: "PENDING_AUTH"` | Sink created, writer identity not authorized in GCP | The `gcloud` grant from setup never ran — resume `perseaai-agents-setup` |
| 4 | `status: "NO_DATA"` and `last_activity_at` is null | Not one log ever arrived | The PR may be unmerged or undeployed, or the API key/endpoint is wrong. Resume `perseaai-agents-setup` to re-validate against a **real emitted line**, not a hand-written sample |
| 5 | `status: "ACTIVE"` but `last_activity_at` older than 24h | Logs were arriving and stopped | Check the most recent deploy |
| 6 | `errors_received: 0`, service active and recent | **Healthy.** No errors yet | Say so as good news. Offer to trigger a real error if they want an end-to-end proof |
| 7 | `errors_received > 0`, `issues_grouped: 0` | Logs arrive but nothing groups | Severity below ERROR, or the entry shape does not validate. Resume `perseaai-agents-setup` to check the wire format |
| 8 | `stats.classifier` is `null` | **Off, not broken** | Say it is disabled. Do not diagnose further down |
| 9 | `classified: 0` with `unidentified > 0` | The classifier runs but cannot classify | Missing repo context or code snippet |
| 10 | `stats.debugger` is `null` | **Off, not broken** | Same as row 8 |
| 11 | `classified > 0`, `approved: 0`, `needs_attention: 0` | May be legitimate: the debugger skips `complex` issues | Call `list_debugger_runs` to confirm whether any run happened at all |
| 12 | `needs_attention > 0` | Runs ended without a fix | Call `list_debugger_runs` and read `termination_reason` |
```

- [ ] **Step 4: Escribir la Fase 2 y las tres trampas**

```markdown
## Phase 2: Report

Narrate the funnel in order: errors received → issues grouped → classified →
debugger runs → PRs awaiting review → resolved. Close with `summary`
(`auto_resolve_rate`, `mean_time_to_fix_hours`, `awaiting_review`) and with
`agents[]`: what is running right now.

If the user then asks about one specific case, drill down: call
`get_project_issue` for an error's full history, or call `list_debugger_runs`
for what the debugger has been doing.

**`awaiting_review` is the actionable number, not a statistic.** Those are pull
requests the debugger opened that are waiting on a human. End the report
pointing there, not at whichever number is largest.

## Three traps

1. **A disabled module reports `null`, not `0`.** `classifier: null` means
   off; `classifier: {"classified": 0}` means on and having classified
   nothing. Confusing them produces exactly the wrong diagnosis. Check
   `module_flags` before reading any counter as a failure.
2. **`agents[].state` is the truth, not `last_event_at`.** The platform
   already applies a 30-minute staleness cut so an abandoned run does not
   report as working. Read `state`; do not recompute it from the timestamp.
3. **Counters are cached for 60 seconds.** If the user just deployed,
   re-polling every few seconds tells them nothing new. Wait, and say that is
   what you are doing.
```

- [ ] **Step 5: Correr los dos validadores**

```bash
python3 scripts/validate_skill.py skills/perseaai-agents-status/SKILL.md
python3 scripts/validate_tool_references.py skills/perseaai-agents-status/SKILL.md
```

Esperado: `OK: skills/perseaai-agents-status/SKILL.md` de ambos.

Si el segundo se queja de una tool no declarada, la causa es una celda de la tabla escrita con el idiom ``call `x``` sobre una tool de onboarding. Reescribir la celda como derivación; no agregar la tool a Prerequisites.

- [ ] **Step 6: Verificar que la skill de setup sigue validando**

```bash
python3 scripts/validate_skill.py skills/perseaai-agents-setup/SKILL.md
python3 scripts/validate_tool_references.py skills/perseaai-agents-setup/SKILL.md
```

Esperado: ambos OK, sin cambios en ese archivo.

- [ ] **Step 7: Commit**

```bash
git add skills/perseaai-agents-status/SKILL.md
git -c user.name="Cristhian Arboleda" -c user.email="casboleda@avocadoblock.com" \
  commit -m "feat: skill perseaai-agents-status para monitorear el pipeline de un proyecto"
```

---

### Task 5: Empaquetado y prueba de campo

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: la skill de la Tarea 4.
- Produces: el plugin `perseaai-agents-dev` 0.4.0 instalable con las dos skills.

- [ ] **Step 1: Bumpear el plugin**

En `.claude-plugin/plugin.json`, subir `version` de `"0.3.0"` a `"0.4.0"` y extender la `description` para que nombre las dos capacidades:

```json
{
  "name": "perseaai-agents-dev",
  "version": "0.4.0",
  "description": "Onboard projects onto the Persea AI agents platform and monitor their pipeline: connect GitHub, register services, integrate logcore structured logging, and check logs, classifier verdicts and debugger runs (canal de desarrollo — API dev).",
  "author": {
    "name": "Avocado Blockchain Services",
    "email": "support@avocadoblock.com"
  }
}
```

`.mcp.json` no se toca: la clave `perseaai-agents-dev` y la URL son las mismas.

- [ ] **Step 2: Actualizar el README**

En la sección "Repository layout", agregar la línea de la skill nueva debajo de la existente:

```markdown
- `skills/perseaai-agents-status/SKILL.md` — la skill de monitoreo post-setup
```

Y en "Usage", después del párrafo de `perseaai-agents-setup`, agregar:

```markdown
Una vez integrado el proyecto, para saber si está funcionando:

> "¿Está llegando algo a la plataforma desde este repo?"
> "¿Cómo va mi proyecto?"

La skill `perseaai-agents-status` se dispara sola: diagnostica el pipeline
cuando todavía no hay datos, y reporta logs, veredictos del classifier, runs
del debugger y PRs esperando review cuando sí los hay.
```

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json README.md
git -c user.name="Cristhian Arboleda" -c user.email="casboleda@avocadoblock.com" \
  commit -m "chore: plugin 0.4.0 con la skill de estado"
```

- [ ] **Step 4: Push y PR**

```bash
git push
gh pr create --base development \
  --title "feat: skill perseaai-agents-status" \
  --body "Segunda skill del plugin: monitorea el pipeline de un proyecto despues del onboarding. Diagnostica cuando no hay datos y reporta cuando si los hay.

Depende de las tres tools MCP de lectura en persea-agents-api (\`get_project_status\`, \`get_project_issue\`, \`list_debugger_runs\`).

Spec: \`docs/superpowers/specs/2026-08-21-project-status-skill-design.md\`
Plan: \`docs/superpowers/plans/2026-08-21-project-status-skill.md\`

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 5: Prueba de campo del trigger**

Este es el riesgo real de tener dos skills en el mismo plugin, y no lo cubre ningún test. En una **sesión limpia** con el plugin reinstalado desde la rama:

1. Preguntar *"¿cómo va mi proyecto?"* → tiene que cargar `perseaai-agents-status`.
2. Preguntar *"conectá este repo a la plataforma"* → tiene que cargar `perseaai-agents-setup`, **no** la nueva.
3. Sobre un proyecto activo sin errores, confirmar que reporta **sano** y no una falla.
4. Sobre un proyecto con el debugger apagado, confirmar que dice **apagado** y no cero.

Si (1) o (2) cargan la skill equivocada, el arreglo es el `description`, no el cuerpo: es lo único que el agente lee para decidir.
