# Stack orchestration — what was verified, and what was not

Branch: `arena/913cb541-wbalc`. Written 2026-11-19.

## What exists

| Entry point | Scope |
| --- | --- |
| `./scripts/dev.sh up` | Docker: engine + Next.js UI (+ `--research`, `--postgres`, `--all`, `--build`) |
| `./scripts/up.sh up` | Native: same services without Docker (+ `--research`, `--dev` for reload/HMR) |
| `docker compose up -d` | Still works directly; the profiles are unchanged |

`docker-compose.yml` before this change already described four services, but had
three defects that made the "optional" paths silently wrong:

1. **Postgres started and was ignored.** `db` was in the `postgres` profile but
   nothing set `DATABASE_URL`, so `--profile postgres up` looked like a Postgres
   deployment while the engine kept writing SQLite inside `rsal-data`. Data
   written under that assumption disappears if the volume is recreated.
   `DATABASE_URL` is now passed through and `scripts/dev.sh --postgres` refuses
   to start without it, naming the exact line to add to `.env`.
2. **The API healthcheck proved too little.** It fetched `/health`, which passes
   on an image missing `libgomp.so.1`; the first LightGBM fit is what fails.
   The probe now also imports `lightgbm, sklearn, rasterio`.
3. **Ports were hard-coded** (`8000`, `3000`, `5173`), so a stack could not be
   started twice, and a stale dev server produced a bare `bind: address already
   in use`. They are now `API_PORT`/`FRONTEND_PORT`/`RESEARCH_PORT`, and
   `dev.sh` reports which pid holds a busy port before starting anything.

Also added: `name: wbalc` (so volumes are namespaced), image tags, `db` restart
policy, `pg_isready` against the configured user/database, and a `research`
healthcheck inherited from its Dockerfile.

## Verified (actually executed)

```
./scripts/up.sh up --research           # cold start of all three services
  ✓ engine started (pid …)  ✓ engine is up: http://localhost:8000/health
  ✓ frontend started        ✓ Next.js workspace is up: http://localhost:3000/
  ✓ research started        ✓ research workspace is up: http://localhost:5173/

./scripts/up.sh status                  # 3 services up, pid files match the
                                        # processes actually holding the ports
./scripts/up.sh down                    # no listening sockets left, no orphans

.venv/bin/python scripts/frontend_smoke.py --base http://localhost:3000
                                        # 69 checks passed
.venv/bin/python scripts/research_frontend_smoke.py --base http://localhost:5173
                                        # 140 checks passed
.venv/bin/python -m pytest -p no:warnings
                                        # 353 passed in 142.39s
cd frontend && npm test                 # 25 tests passed
bash -n scripts/dev.sh scripts/up.sh    # both parse
```

`tests/test_compose_stack.py` (17 tests) validates the compose file and both
launchers without a daemon: service/dependency coherence, profiles, healthcheck
gating (`service_healthy`, not `service_started`), build contexts and
Dockerfiles present, volumes for persistent data, configurable ports, and that
`dev.sh` exits non-zero with actionable text when Docker is absent.

## Bugs this work found (pre-existing, not introduced here)

Running the stack end-to-end is what surfaced them:

1. **`scripts/frontend_smoke.py` could not create a project.** It predates the
   Phase 1 water taxonomy: the engine now rejects any class list other than
   `open_water, emergent_vegetation, land` unless `generic_classes=true`, so the
   smoke died at check 2 of 69.
2. **The Next.js adapter dropped `genericClasses`**, so a caller with its own
   class list had no way to create a project through the UI's API — the engine
   offering `generic_classes` was unreachable from the browser. Now forwarded.
3. **The smoke fixture declared no band names**, so training failed with the
   (correct) Phase 0 refusal: "None of the contributing rasters declares band
   names". The fixture now sets band descriptions, as a real Sentinel stack does.

## NOT verified — needs a Docker daemon

**No image was built and no container was run.** This sandbox has no Docker
daemon (`docker: command not found`), so the container path is validated only by
`docker-compose.yml` parsing plus the structural assertions above. Specifically
unverified:

- that `./scripts/dev.sh up` starts a working stack on a real daemon,
- that the API image's `libgomp1` install still satisfies LightGBM in a fresh
  build,
- that the Next.js standalone image serves assets correctly in-container,
- `--postgres`: the SQLite→Postgres path is exercised by the application tests
  against SQLite only; no Postgres container was started.

The **native** path (`./scripts/up.sh`) is fully verified, as listed above.
Anyone who runs the Docker path should treat the first `--build` as the real
test; `./scripts/dev.sh ps` and the API healthcheck exist to make a bad image
fail loudly rather than at the first training run.
