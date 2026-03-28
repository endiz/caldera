# Caldera repository instructions

## Build, test, and lint commands

- Install Python dependencies with `pip install -r requirements.txt -r requirements-dev.txt`.
- Start the server with the built UI using `python3 server.py --insecure --build`.
- Run the Vue UI in dev mode with `python3 server.py --uidev localhost`. This expects the `plugins/magma` submodule to exist.
- Build Magma directly with `npm --prefix plugins/magma install && npm --prefix plugins/magma run build`. CI does this before running `tox`.
- Run the full Python test suite with `python -m pytest --asyncio-mode=auto`.
- Run one test file with `python -m pytest tests/api/v2/handlers/test_abilities_api.py --asyncio-mode=auto`.
- Run one test with `python -m pytest tests/api/v2/handlers/test_abilities_api.py::test_ability --asyncio-mode=auto`.
- Run the multi-environment test matrix locally with `tox`, or a single env with `tox -e py311`.
- Run repository-wide style checks with `tox -e style` (this executes `pre-commit run --all-files --show-diff-on-failure`).
- Root frontend linting only covers the legacy UI in `static/` and `templates/`: `npm run lint-js` and `npm run lint-css`.
- Magma has its own frontend tooling under `plugins/magma/`: `npm --prefix plugins/magma run lint`, `npm --prefix plugins/magma run test`, and a single Jest file with `npm --prefix plugins/magma run test -- src/tests/LoginView.test.js`.
- Run the security checks used in CI with `tox -e safety` and `tox -e bandit`.

## High-level architecture

- `server.py` is the entrypoint. It loads `conf/*.yml` into `BaseWorld`, instantiates service singletons, creates the aiohttp application, mounts the `/api/v2` subapp, restores persisted state, registers contacts, loads plugins, loads YAML-backed data, runs plugin expansions, and starts long-lived background tasks.
- `app/service/` contains the long-lived managers. `AppService` owns plugin loading, Jinja setup, scheduler/resume/watcher tasks, and teardown. `DataService` is the center of persistence: it keeps first-class objects in `self.ram`, loads YAML from `data/` and enabled plugin `data/` folders, and saves runtime state to `data/object_store` on shutdown.
- `app/objects/` holds first-class domain objects such as `Ability`, `Adversary`, `Agent`, `Operation`, `Planner`, `Plugin`, and `Objective`. `app/objects/secondclass/` holds nested pieces such as `Executor`, `Link`, `Fact`, `Relationship`, `Parser`, and `Requirement`.
- Two web surfaces coexist:
  - The legacy/root app in `app/api/rest_api.py` plus `app/api/packs/*` serves login/logout, `/api/rest`, `/campaign/*`, `/advanced/*`, file endpoints, and older Jinja-driven views.
  - The newer REST API lives under `app/api/v2/` and is split into handlers, managers, schemas, and middleware. Every v2 handler is registered in `app/api/v2/__init__.py`.
- Frontend code is split between the Vue-based Magma UI in `plugins/magma/` and older Jinja/static assets in `templates/`, `static/`, and plugin-specific `templates/` / `static/` folders. The built Magma app is served from `plugins/magma/dist`, while the root `package.json` only lints the legacy frontend.
- Plugins are first-class extensions. Each plugin lives under `plugins/<name>/`, must provide `hook.py`, and typically exposes `name`, `description`, optional `address` / `access`, `async def enable(services)`, and sometimes `expansion(services)` or `destroy(services)`. Plugin data directories (`abilities`, `adversaries`, `objectives`, `planners`, `sources`, etc.) are loaded automatically.

## Key conventions

- Clone recursively and keep submodules intact. `AppService.load_plugins()` expects `plugins/<name>/hook.py` to exist and exits early when a configured plugin cannot be found.
- `BaseWorld.apply_config(..., apply_hash=True)` can rewrite config files to hash credentials and API keys. Do not assume plain-text values from `conf/*.yml` survive first startup or test setup unchanged.
- Services are global singletons registered through `BaseService.add_service()` and retrieved with `get_service()` / `get_services()`. New service code should follow that registry pattern instead of passing service objects deep through the stack.
- Model objects are schema-driven. First-class objects normally define a Marshmallow `schema`, optional `display_schema`, a `unique` property, and `store(self, ram)` for in-memory upsert behavior. Most API responses should come from `.display`, not hand-built dicts.
- Access levels are part of the data model. Plugins declare `BaseWorld.Access.*`, loaded YAML objects inherit plugin access, and some `expansion()` hooks mutate access after load (for example, training hides its loaded abilities and adversaries).
- Magma is special-cased: `AppService.load_plugins()` enables it whenever the plugin exists, even though it is not listed in `conf/default.yml`.
- V2 API CRUD is file-backed. Handlers in `app/api/v2/handlers/` delegate create/update/delete work to managers in `app/api/v2/managers/`; they should not bypass that logic and mutate `DataService.ram` directly when persistence is required.
- Abilities are special within v2 CRUD: they are saved under `data/abilities/<tactic>/<id>.yml`, tactic names are normalized to lowercase, moving an ability to a different tactic changes its file path, and ability changes also refresh the generated "Everything Bagel" adversary.
- Ability YAML uses `id`, while the Python object field and v2 route key are `ability_id`. The ability schema, data loader, and v2 manager translate between them; preserve that mapping when touching ability APIs or YAML loaders.
- `DataService` still normalizes legacy YAML shapes. It accepts `id` as the source identifier, converts adversary `phases` to `atomic_ordering`, and supports both legacy and current executor/requirement formats. Preserve backward compatibility when touching loaders or schemas.
- Runtime template loading is not the same as test setup. `AppService` loads enabled plugin templates plus `plugins/magma/dist`, while `tests/conftest.py` explicitly appends root `templates/` and manually wires `RestApi` plus `/api/v2` routes. Keep that difference in mind when changing legacy pack views or Jinja resolution.
- `AppService.watch_ability_files()` hot-reloads changed YAML from enabled plugin data directories and root `data/abilities` on the configured `ability_refresh` interval. Editing ability YAML can change server behavior without a restart.
- The repository has two frontend toolchains. Root `package.json` scripts target legacy `static/` and `templates/`, while `plugins/magma/package.json` owns Vue build/lint/test commands. Use the matching toolchain for the files you change.
- Tests rely heavily on `tests/conftest.py` fixtures and async helpers. API tests usually use `api_v2_client` / `aiohttp_client`; service tests commonly store objects in `DataService` directly and patch async boundaries with `AsyncMock` or `unittest.mock`.
