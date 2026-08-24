# perseaai-agents-status — Design Spec

**Date:** 2026-08-21
**Status:** Approved for implementation
**Owner:** Cristhian
**Channel:** rama `development` (plugin `perseaai-agents-dev`, MCP `perseaai-agents-dev`)

## Overview

Una segunda skill en este repo, `perseaai-agents-status`, que responde dos preguntas que
hoy nadie contesta desde la terminal:

1. *"Hice el setup ayer. ¿Está funcionando de verdad?"*
2. *"¿Cómo va mi proyecto — cuántos errores agrupó, qué clasificó, qué arregló el
   debugger, qué PR está esperándome?"*

El spec original de este repo (`2026-08-17-abs-agents-skills-design.md`) listaba
*"a troubleshooting skill"* como non-goal explícito de aquella iteración. Esto es ese
follow-up.

La skill se apoya en datos que **ya existen y ya se calculan** en `persea-agents-api`:
`StatsService` alimenta `GET /v1/projects/{project_id}/stats` con `ClassifierStats`,
`DebuggerStats`, `LogsStats`, `ResultsStats`, `SummaryStats` y `AgentState`. Lo que no
existe es una vía MCP para leerlos: el servidor lite solo expone herramientas de
onboarding, ninguna de lectura. Este trabajo agrega esa vía y luego escribe la skill
contra ella.

## Goals

- Tres tools de lectura en el MCP lite de `persea-agents-api`, autenticadas y sin
  escrituras.
- Una skill `perseaai-agents-status` que resuelve sola en qué fase está el proyecto
  (diagnóstico vs reporte) sin preguntárselo al usuario.
- Un diagnóstico que distingue las cinco causas distintas de un contador en cero.
- Convivencia limpia con `perseaai-agents-setup`: dos skills en el mismo plugin, cada
  una con su trigger, sin solaparse.

## Non-goals

- Cambiar `StatsService` o el cálculo de cualquier métrica. Este trabajo lee lo que hay.
- Tools de escritura por MCP (reintentar un run, cerrar un issue, togglear un módulo).
- Un modo "watch" o polling continuo. La skill responde cuando se le pregunta.
- Tocar `perseaai-agents-setup`, más allá de no pisarle el trigger.

## Naming

| Cosa | Nombre |
|---|---|
| Skill | `perseaai-agents-status` |
| Carpeta | `skills/perseaai-agents-status/SKILL.md` |
| Plugin (canal dev) | `perseaai-agents-dev` — bump `0.3.0` → `0.4.0` |
| MCP server key | `perseaai-agents-dev` (sin cambios en `.mcp.json`) |
| Versión de la skill | `metadata.version: "0.1.0"` |

`perseaai-agents-setup` conserva su `metadata.version: "0.3.4"` sin tocar.

## Parte 1 — Tools MCP en `persea-agents-api`

Archivo nuevo `src/mcp/tools/project_status.py`, registrado en `src/mcp/lite.py` y
`src/mcp/full.py`. Las tres llaman a `require_mcp_auth()` y resuelven la organización
desde la membresía del caller, sin recibirla como argumento — el patrón que ya usa
`get_service_config_tool`.

Son lectura pura. La tenencia ya la imponen los servicios que envuelven (un proyecto
ajeno responde igual que uno inexistente), así que las tools no reimplementan los checks:
traducen la `HTTPException` 404 a un `ValueError` con mensaje, como el resto del módulo
MCP.

### `get_project_status(project_id)`

La llamada que responde el 90% de los casos. Compone en una respuesta lo que hoy está
repartido entre tres lugares:

- **`stats`** — `ProjectStatsResponse` tal cual sale de `StatsService.get_project_stats`:
  `logs` (`errors_received`, `issues_grouped`), `classifier` (`classified`,
  `unidentified`), `debugger` (`approved`, `needs_attention`), `results` (`resolved`),
  `summary` (`errors_resolved`, `auto_resolve_rate`, `mean_time_to_fix_hours`,
  `awaiting_review`) y `agents[]` (`agent`, `enabled`, `state`, `active_runs`,
  `last_event_at`).
- **`module_flags`** — los flags resueltos (`logs_enabled`, `classifier_enabled`,
  `debugger_enabled`). Sin esto el agente no puede distinguir *roto* de *apagado*.
- **`services[]`** — por service: `service_id`, `repo_full_name`, `branch`,
  `service_type`, `status` (`NO_DATA` / `ACTIVE`), `infra_status`, `last_activity_at`,
  `pr_url`.

Reusa `StatsService` sin modificarlo, incluido su caché Redis de 60 s. Lo único
verdaderamente nuevo es la composición y el bloque `services[]`: `last_activity_at` hoy
no sale por ninguna tool MCP y es la señal que separa "nunca llegó un log" de "llegaban y
se cortaron".

### `get_project_issue(project_id, fingerprint)`

Envuelve `ProjectIssueService.get_for_project`. Devuelve `ProjectIssueDetail`:
`complexity`, `outcome`, `pr_urls`, `runs[]` con sus `steps[]`. Es el drill-down de
*"¿por qué ese error sigue abierto?"*.

### `list_debugger_runs(project_id, status=None, limit=20)`

Envuelve `DebuggerRunService.list_for_project`. Devuelve `DebuggerRunSummary[]`:
`status`, `termination_reason`, `cost_usd`, `cycles_used`, `pr_url`, `producer`,
`started_at`, `finished_at`. Es el drill-down de *"¿qué está haciendo el debugger?"*.

### Tests

En `tests/unit/mcp/`, siguiendo el patrón de los que ya están ahí:

- sin usuario autenticado, cada tool falla;
- un proyecto de otra organización responde como inexistente;
- la composición trae `services[]` con `last_activity_at` poblado;
- **un módulo apagado devuelve `null`, no `0`** — la distinción de la que depende todo
  el diagnóstico de la Parte 2.

`ruff` y `mypy` en verde localmente antes de commitear.

## Parte 2 — La skill

Archivo único `skills/perseaai-agents-status/SKILL.md`, formato agentskills.io, mismo
frontmatter que la existente (`name`, `description`, `license`, `metadata`).

### Trigger

El `description` es lo que decide cuándo se carga la skill, así que cubre las dos fases
sin usar ni una palabra del vocabulario de onboarding. `connect`, `integrate`, `register`
y `set up` quedan exclusivas de `perseaai-agents-setup`; esta skill habla de `check`,
`status`, `working`, `stats`, `monitor`.

Texto:

> Use when the user wants to check whether a project's logcore integration is actually
> working after setup, or wants the current state of a project on the Persea AI agents
> platform — logs arriving, issues grouped, classifier verdicts, debugger runs, PRs
> awaiting review. Requires the platform MCP server to be connected.

### Prerequisites

Nombra las tres tools nuevas más `list_projects`, y si no están en la sesión la skill
**para** y manda al README del plugin, en vez de improvisar con curl. Es el mismo corte
que hace la skill de setup.

Las acciones correctivas de la tabla de Fase 1 mencionan `get_infra_setup` y
`validate_setup`, que pertenecen al flujo de onboarding. La skill **no las invoca**: en
esos casos deriva a `perseaai-agents-setup`, que ya las declara y las sabe usar en
contexto. En la práctica eso significa que el SKILL.md nunca escribe ``call
`get_infra_setup``` — porque `validate_tool_references.py` obligaría entonces a
declararlas en Prerequisites, y una skill que declara tools que no usa es exactamente la
deriva que ese validador existe para atrapar. La redacción de esas celdas es una
derivación ("el setup del sink quedó a medias: retomá `perseaai-agents-setup`"), no una
instrucción de llamada.

### Fase 0 — resolver el proyecto

`list_projects`, y cruzar `repo_full_name` contra el `git remote -v` local. Un solo match
sigue derecho. Cero o varios matches: pregunta. No adivina.

### La bifurcación

Con `get_project_status` en mano la skill elige fase sola, sin preguntar:

- algún service en `NO_DATA`, **o** `stats.logs` es `null`, **o**
  `stats.logs.errors_received == 0` → **Fase 1**
- ya hay datos → **Fase 2**

`stats.logs` puede venir en `null` (módulo de logs apagado), así que la condición se lee
en ese orden: primero se comprueba que el objeto exista y recién después su contador.
Leerlo al revés rompe la skill justo en el proyecto que menos datos tiene.

Fase 1 no significa "algo está roto". Puede terminar perfectamente en *"todo bien,
todavía no hubo errores"* — ver la fila 6 de la tabla.

### Fase 1 — diagnóstico

Se recorre en orden y **se para en el primer eslabón que falla**. Reportar tres problemas
cuando el segundo es consecuencia del primero es como estas skills se vuelven ruido.

| # | Condición | Lectura | Acción |
|---|---|---|---|
| 1 | `pr_url` es null | La integración nunca se completó | Volver a `perseaai-agents-setup` |
| 2 | `infra_status: NOT_CONFIGURED` (solo backends) | Falta el sink de Cloud Logging | `get_infra_setup` |
| 3 | `infra_status: PENDING_AUTH` | Sink creado, falta autorizar el writer identity en GCP | El comando `gcloud` del setup |
| 4 | `status: NO_DATA` y `last_activity_at` null | Nunca llegó un solo log | PR sin mergear/desplegar, API key o endpoint mal → `validate_setup` con una línea **real emitida** |
| 5 | `status: ACTIVE` pero `last_activity_at` > 24 h | Llegaban logs y se cortaron | Revisar el último deploy |
| 6 | `errors_received: 0`, service activo y reciente | **Sano.** No hubo errores todavía | Decirlo como buena noticia; ofrecer provocar uno real para probar end-to-end |
| 7 | `errors_received > 0`, `issues_grouped: 0` | Los logs llegan pero no agrupan | Severity por debajo de ERROR, o el shape no valida → `validate_setup` |
| 8 | `classifier` es `null` (módulo apagado) | **Apagado, no roto** | Decirlo; no diagnosticar más abajo |
| 9 | `classified: 0` con `unidentified > 0` | El classifier corre pero no logra clasificar | Falta contexto de repo / snippet |
| 10 | `debugger` es `null` (módulo apagado) | **Apagado, no roto** | Ídem |
| 11 | `classified > 0`, `approved: 0`, `needs_attention: 0` | Puede ser legítimo: el debugger salta los `complex` | `list_debugger_runs` para confirmar si hubo runs |
| 12 | `needs_attention > 0` | Hubo runs que terminaron sin fix | `list_debugger_runs` + leer `termination_reason` |

### Fase 2 — reporte

Narra el embudo en orden: errores recibidos → issues agrupados → clasificados → runs del
debugger → PRs esperando review → resueltos. Cierra con `summary` (`auto_resolve_rate`,
`mean_time_to_fix_hours`, `awaiting_review`) y con `agents[]`: qué está corriendo ahora.

De ahí, si el usuario pregunta por un caso concreto, drill-down con `get_project_issue` o
`list_debugger_runs`.

Regla explícita en el SKILL.md: **`awaiting_review` es la métrica accionable**, no una
estadística. Son PRs abiertos por el debugger esperando a un humano. El reporte termina
apuntando ahí, no en el número más vistoso.

### Tres trampas que van escritas aparte

1. **Módulo apagado devuelve `null`, no `0`.** `classifier: null` es apagado;
   `classifier: {classified: 0}` es encendido y sin clasificar nada. Confundirlos produce
   exactamente el diagnóstico equivocado.
2. **`agents[].state` es la verdad, no `last_event_at`.** La API ya aplica su corte de
   30 minutos (`STALE_AFTER`) para no reportar como "trabajando" un run abandonado. La
   skill lee `state` y no recalcula nada desde el timestamp.
3. **Los contadores tienen caché de 60 s.** Si el usuario acaba de desplegar, repolear
   cada 5 segundos no sirve. La skill espera y lo dice.

## Orden de trabajo

1. **`persea-agents-api`**, rama `feat/mcp-project-status` desde `development`: las tres
   tools, su registro en `lite.py` y `full.py`, y los tests. PR a `development`.
2. **Deploy a dev y verificación real** contra un proyecto que ya tenga issues y runs.
   Las tools no se dan por buenas hasta ver datos verdaderos saliendo del MCP.
3. **`abs-agents-skills`**, rama `feat/project-status-skill` desde `development`: la
   carpeta nueva, README actualizado, `plugin.json` `0.3.0` → `0.4.0`.
4. **Los dos validadores del repo en verde**: `scripts/validate_skill.py` (frontmatter, y
   `name` idéntico al nombre de carpeta) y `scripts/validate_tool_references.py`, que
   exige que cada tool invocada en el cuerpo con el idiom ``call `tool``` esté declarada
   en Prerequisites, y al revés. Eso condiciona cómo se redacta el markdown; no es un
   chequeo cosmético.
5. **Prueba de campo**: sesión limpia, preguntar *"¿cómo va mi proyecto?"* y confirmar que
   dispara `perseaai-agents-status` y no la de setup. Es el riesgo real de tener dos
   skills en el mismo plugin.

## Criterios de aceptación

- Las tres tools aparecen en una sesión con el MCP `perseaai-agents-dev` conectado.
- En un proyecto recién dado de alta y sin desplegar, la skill dice *"la integración
  nunca se completó / no llegó ningún log"*, y **no** dice que el classifier esté roto.
- En un proyecto activo y sin errores, la skill lo reporta como **sano**, no como falla.
- En un proyecto con el debugger apagado, la skill dice *apagado*, no *cero*.
- En un proyecto con datos, el reporte termina apuntando a `awaiting_review`.
- Preguntar *"conectá este repo a la plataforma"* sigue disparando
  `perseaai-agents-setup`, no la nueva.
