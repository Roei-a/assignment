# Epoch & Now-Time Services — Monorepo

Two small REST services, a local integration environment, and a CI pipeline.

- **epoch-service (Service A)** — self-contained; converts an ISO-8601 date to
  a Unix epoch timestamp. Knows about no other service.
- **now-time-service (Service B)** — returns the current UTC time, and can ask
  Service A to convert that time into an epoch (`GET /now-epoch`).

`GET /now-epoch` on Service B is what the integration tests use to validate
service-to-service communication: B fetches the current time, sends it to A's
`/epoch`, and returns the result.

## Repository structure

```
.
├── services/
│   ├── epoch-service/        # Service A
│   │   ├── app/              # Application code
│   │   ├── config/           # config.yaml
│   │   ├── tests/            # Unit tests
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── now-time-service/     # Service B (same layout)
├── tests/integration/        # Cross-service integration tests
├── docker-compose.yml        # Local integration environment
├── Makefile                  # Single entry point for all workflows
├── requirements-dev.txt      # Dev/test tooling (pytest, ruff)
└── .github/workflows/ci.yml  # CI pipeline
```

## Prerequisites

- Docker (with the Compose plugin) — for the integration environment
- Python 3.9+ — for running tests / services directly on the host
- `make`

## Quick start

```bash
make up                 # build and start both services, wait until healthy

# Service A — convert a date to epoch
curl -s -X POST localhost:8080/epoch \
  -H 'Content-Type: application/json' \
  -d '{"date": "2026-06-15T10:00:00Z"}'
# => {"epoch": 1781517600}

# Service B — current time, and current time converted via Service A
curl -s localhost:8081/now         # => {"now": "2026-07-18T08:07:23Z"}
curl -s localhost:8081/now-epoch   # B calls A: {"now": "...", "epoch": ...}
make down
```

Run `make` (or `make help`) to see every available target.

## API

### Error format (both services)

Every error response is a JSON object carrying the HTTP status **code**
alongside the message, so the code is available in the body as well as the
status line:

```json
{ "code": 400, "error": "<human-readable explanation>" }
```

This applies uniformly, including framework errors like `404` (unknown route)
and `405` (wrong method). Where a request body is expected, the error also
includes a real, copy-pasteable `example` object:

```json
{ "code": 400, "error": "Request body is empty: ...", "example": { "date": "2026-06-15T10:00:00Z" } }
```

### epoch-service — Service A (port 8080)

Self-contained. Takes a date, returns an epoch. No outbound dependencies. The
body is parsed as JSON regardless of the `Content-Type` header.

| Method | Path       | Description                                        |
|--------|------------|----------------------------------------------------|
| POST   | `/epoch`   | Body `{"date": "<ISO-8601>"}` → `{"epoch": <int>}` |
| GET    | `/healthz` | Health check                                       |

Failure modes return a clear JSON error (`400` with `code` + `example`):

| Case                               | Status | Error message                          |
|------------------------------------|--------|----------------------------------------|
| Empty body                         | 400    | "Request body is empty: ..."           |
| Body is not valid JSON             | 400    | "Request body is not valid JSON: ..."  |
| Not an object with a string `date` | 400    | "Request body must be a JSON object ..." |
| Unparseable date                   | 400    | "Invalid date '...': expected ISO-8601" |

### now-time-service — Service B (port 8081)

Reports the current time, and can convert it to epoch via Service A.

| Method | Path         | Query      | Description                                    |
|--------|--------------|------------|------------------------------------------------|
| GET    | `/now`       | `tz` (opt) | `{"now": "<current time, ISO-8601>"}`          |
| GET    | `/now-epoch` | `tz` (opt) | Calls Service A → `{"now": ..., "epoch": ...}` |
| GET    | `/healthz`   | —          | Health check                                   |

**Timezone.** The time is reported in a timezone chosen as follows:

- Default comes from config (`time.default_timezone`, an IANA name, defaults to `UTC`).
- Override per request with `?tz=<IANA name>`, e.g. `/now?tz=America/New_York`.
- UTC is rendered as `...Z`; other zones carry their offset, e.g. `...+03:00`.
- An unknown zone returns `400` with an explanation.
- Note: `/now-epoch`'s `epoch` is **unchanged** by timezone — epoch is an
  absolute instant; only the human-readable `now` string differs.

```bash
curl -s 'localhost:8081/now'                       # {"now": "2026-07-18T08:26:09Z"}
curl -s 'localhost:8081/now?tz=Asia/Tokyo'         # {"now": "2026-07-18T17:26:09+09:00"}
curl -s 'localhost:8081/now-epoch?tz=Asia/Tokyo'   # {"now": "...+09:00", "epoch": 1784363169}
```

Every `/now-epoch` failure returns both a status code and an explanation of the
likely cause:

| Case                                    | Status | Explanation                                    |
|-----------------------------------------|--------|------------------------------------------------|
| Unknown `tz` value                      | 400    | "Unknown timezone ... expected an IANA name"   |
| Service A unreachable                   | 502    | "Could not reach epoch-service ... probably not running" |
| Service A returned a non-200 status     | 502    | "epoch-service returned an unexpected status ..." |
| Service A returned an unexpected body   | 502    | "... the two services may be out of sync"      |

## Configuration

Each service is fully driven by a **single** YAML config file
(`config/config.yaml`) controlling the bind address, port, and endpoint paths.
Service B additionally configures the epoch-service URL
(`dependencies.epoch_service_url`) and the default timezone
(`time.default_timezone`). A different file can be supplied via the
`CONFIG_PATH` environment variable.

The one value that genuinely differs between running on the host and running in
Docker is Service B's downstream URL. Rather than duplicate the whole file per
environment, the config holds the host default (`http://localhost:8080`) and
Docker Compose overrides just that value with the `EPOCH_SERVICE_URL`
environment variable (pointing at the Compose DNS name `http://epoch-service:8080`).
This is the 12-factor pattern: config file for defaults, environment for the
per-deployment override.

## Running the services

**Both together (recommended):**

```bash
make up      # docker compose up -d --build --wait
make logs    # tail logs
make down    # tear down
```

**Individually on the host (no Docker):**

```bash
make run-epoch      # port 8080 (Service A — standalone)
make run-now-time   # port 8081 (Service B — needs Service A on 8080 for /now-epoch)
```

### Image architecture

By default, images are built for the **host architecture** — `make up` and
`docker compose up --build` need no extra flags. To target a specific
architecture there are two options:

```bash
make up ARCH=amd    # force linux/amd64
make up ARCH=arm    # force linux/arm64
make up             # host architecture (default)
```

`ARCH` simply exports `DOCKER_DEFAULT_PLATFORM` for the build. Alternatively,
each service in `docker-compose.yml` has a commented `platform:` line you can
uncomment to pin an architecture statically. Both are left inactive by default
so the host architecture is used.

## Running tests

```bash
make test               # unit tests for both services
make integration-test   # starts the Compose env, tests cross-service comms, tears down
```

## CI pipeline

`.github/workflows/ci.yml`, GitHub Actions.

**On every pull request:**
1. `arch` — resolves which architecture(s) to build/test (PRs → amd64 only).
2. `changes` — detects which services are affected using path filters
   (changes to shared files like the Compose file or CI config affect all services).
3. `format` — `ruff format --check` + `ruff check`.
4. `test` — unit tests, matrixed over **affected services only**.
5. `integration-test` — brings up the Compose environment (building the affected
   services) and runs the cross-service tests. Matrixed over architecture.

**On every push to `main`:** all of the above (now across **both** architectures),
plus `publish` — matrixed over **service × architecture**, it builds a
per-architecture image for each affected service on a native runner, tags it
`<arch>-<commit-sha>` (e.g. `epoch-service:arm64-828d488...`), and **simulates**
pushing it to a registry (prints the `docker push` command; no real registry is
involved, per the assignment).

**Architecture matrix.** The `arch` job decides the target architecture(s) and
emits them as a JSON array (`["amd64","arm64"]`): pull requests use **amd64 only**
(fast feedback); pushes to `main` use **both**; a manual `workflow_dispatch` run
picks `amd` / `arm` / `both` (default `both`). That array drives both the
`integration-test` and `publish` matrices; each short name also selects the
native runner for its leg (amd64 → `ubuntu-latest`, arm64 → `ubuntu-24.04-arm`).

**Everything runs on native runners per architecture** — no emulation. Both
`integration-test` and `publish` run each architecture leg on a matching runner,
so a plain `docker build` / `docker compose up --build` produces the correct
architecture directly.

**Running the CI checks locally:**

```bash
make ci   # fmt-check + lint + unit tests — identical to the PR jobs
```

The pipeline can also be run with [act](https://github.com/nektos/act) if you
prefer executing the actual workflow file locally.

## Assumptions & design decisions

- **now-time-service implementation**: the assignment references provided code
  for Service B ("take this code"), but no code was attached. I asked for it
  and implemented a minimal equivalent in the meantime (returns current UTC
  time as ISO-8601); it can be swapped for the original without changing the
  environment, CI, or tests.
- **Naive datetimes are treated as UTC** (`"2026-06-15T10:00:00"` ==
  `"...T10:00:00Z"`). Dates with an explicit offset are converted correctly.
- **Validation errors return 400** (not FastAPI's default 422) with a
  human-readable `{"error": ...}` message — clearer for API consumers.
- **Direction of the dependency**: Service A (epoch-service) stays pure and
  standalone (exactly Part 1). Service B (now-time-service) is the caller —
  `/now-epoch` fetches the current time and asks A to convert it over the
  Compose network, which the integration test asserts on. Every B→A failure
  returns a 502 with an explanation of the likely cause (A down, A rejected the
  request, or A returned an unexpected body).
- **Python + FastAPI** for both services: small, typed, fast to review, with
  first-class test support. **Docker Compose** over Kubernetes: right-sized
  for a two-service local environment — one command, no cluster required.
- **"Affected services" in CI** is computed from changed paths; shared
  infrastructure files conservatively mark every service as affected.
- **Image publishing is simulated** by printing the `docker push` commands the
  pipeline would run, per the assignment note.
