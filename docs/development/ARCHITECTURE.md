# Architecture Overview

Hofmätteli Telemetry moves entity states between Home Assistant installations through a
[Hofmätteli Telemetry server](https://github.com/herpaderpaldent/hofmaetteli_telemetry), a small FastAPI service that
keeps the latest state of each entity and hands out role-based bearer tokens (`read`, `write`, `readwrite`).

Every config entry runs in one of two modes, stored as `mode` in the entry data:

- **Share** pushes the state of selected local entities to the server. It creates no entities.
- **Receive** polls the server and mirrors selected remote entities as local sensors and binary sensors.

One Home Assistant can hold both kinds of entry, for the same server or different ones.

## Directory Structure

```text
custom_components/hofmaetteli_telemetry/
├── __init__.py              # Setup and unload; branches on the entry's mode
├── config_flow.py           # Discovery shim; the flow lives in config_flow_handler/
├── const.py                 # Domain, mode and option keys, mapped attributes
├── data.py                  # Runtime data on entry.runtime_data
├── diagnostics.py           # Redacted diagnostics
├── manifest.json
├── api/
│   ├── __init__.py          # Exports the client, RemoteEntity and the exceptions
│   └── client.py            # aiohttp client for the server's three endpoints
├── coordinator/
│   ├── __init__.py
│   ├── base.py              # Receive: DataUpdateCoordinator, one GET per minute
│   └── publisher.py         # Share: event-driven publisher, one PUT per state
├── config_flow_handler/
│   ├── config_flow.py       # Mode menu, receive and share steps, reconfigure, reauth
│   ├── options_flow.py      # Change the entity selection (reloads the entry)
│   ├── schemas/config.py    # Connection, token and entity-selection schemas
│   └── validators/
│       └── credentials.py   # Connection check, share token check, initial push
├── entity/
│   └── base.py              # Base for every mirrored entity
├── sensor/
│   ├── __init__.py          # One sensor per selected remote entity outside binary_sensor
│   └── entity.py            # Unit, device class and state class from the remote
├── binary_sensor/
│   ├── __init__.py          # One binary sensor per selected remote binary_sensor.*
│   └── entity.py
├── brand/                   # Integration icon
└── translations/en.json
```

There are no service actions, repairs or `icons.json`. `entity_utils/` and `utils/` are part of the permitted package
set in [`AGENTS.md`](../../AGENTS.md) but do not exist until something needs them.

## Server API

The client in `api/client.py` uses three endpoints:

| Call                        | Used by                              | Token role |
| --------------------------- | ------------------------------------ | ---------- |
| `GET /entities?full=true`   | receive coordinator, receive flow    | `read`     |
| `GET /entities`             | share flow token check (403 is fine) | any        |
| `PUT /entities/{entity_id}` | publisher, share flow initial push   | `write`    |

HTTP status codes become exceptions: 401 → `…AuthenticationError`, 403 → `…ForbiddenError`, 429 →
`…RateLimitError` carrying the `Retry-After` value, network and timeout failures → `…CommunicationError`. Requests
time out after 10 seconds.

## Receive mode

```text
server ──GET /entities?full=true every 60 s──▶ coordinator (base.py)
                                                  │ coordinator.data: {remote entity ID: RemoteEntity}
                                                  ▼
                              sensor / binary_sensor entities (entity/base.py)
```

- **Coordinator** (`HofmaetteliTelemetryDataUpdateCoordinator`): one request per minute fetches every remote entity
  the server has; the entities pick theirs out of `coordinator.data`. A rejected token raises
  `ConfigEntryAuthFailed`, which starts reauth. A rate limit raises `UpdateFailed` with a `retry_after` bounded
  between 10 seconds and ten update intervals.
- **Platforms**: a selected remote entity whose ID starts with `binary_sensor.` becomes a binary sensor; everything
  else becomes a sensor. The sensor reads unit, device class and state class from the remote attributes, so it is a
  numeric, timestamp, date or text sensor depending on what the sender had.
- **Base entity**: unique ID `{entry_id}_{remote_entity_id}`. The name is the remote friendly name, and the device is
  a service device named after the server's host, so entity IDs look like
  `sensor.telemetry_example_org_outdoor_temperature`. Remote attributes not mapped to an entity property are passed
  through, plus `remote_entity_id`, `remote_last_updated` and the server's `stale` flag.
- **Availability**: an entity is unavailable while the coordinator fails or when the server no longer reports its
  remote entity.
- **Deselection**: on setup, registry entries for remote entities no longer selected in the options are removed.

## Share mode

```text
state change of a selected entity ─┐
heartbeat every 4 hours ───────────┼─▶ pending {entity ID: latest State} ──▶ drain task ──PUT, one at a time──▶ server
entry setup (once) ────────────────┘
```

- **Publisher** (`HofmaetteliTelemetryPublisher`): listens to state changes of the selected entities, queues every
  selected entity at start and every 4 hours, and pushes from one drain task, one request at a time. A newer state
  replaces a pending older one, so a busy sensor costs one request per cycle.
- **Filtering**: `unknown` and `unavailable` are never sent, so a restart cannot overwrite the last good value.
  Attributes are converted to plain JSON first.
- **Failures**: a rejected token stops the publisher and starts reauth. A rate limit puts the state back and waits
  the requested time (at most 5 minutes). Any other error drops that push; the next change or heartbeat sends a
  fresh state, and the warning is logged once until pushing works again.
- **Freshness**: `last_changed` is not sent, so the server records when it received each value. The heartbeat then
  keeps unchanged sensors from being flagged `stale` on the receiving side.
- The publisher's listeners and task are tied to the entry and stop when it unloads.

## Config flow

The user step is a menu: receive or share.

- **Receive**: URL, token and SSL check → the server's entity list is fetched (this proves the token can read) →
  the user ticks remote entities → entry titled `Receiving from <host>`. Aborts when the server has no entities yet.
- **Share**: URL, token and SSL check → the token is checked against the read endpoint, where a 403 still proves it
  exists → the user picks local entities → their current states are pushed once, which is the only way to learn
  whether the token may write → entry titled `Sharing to <host>`.
- **Reconfigure** changes URL, token and SSL setting, validated for the entry's mode. **Reauth** asks for a new
  token only. **Options** change the entity selection and reload the entry.

A second entry for the same URL and mode is refused. URLs are normalised (whitespace and trailing slashes removed)
before comparing.

## Runtime data

`entry.runtime_data` is a `HofmaetteliTelemetryData` with the API client and the loaded integration, plus either a
`coordinator` (receive) or a `publisher` (share).

## Diagnostics

`diagnostics.py` redacts the URL and the token and reports, depending on the mode, the coordinator's state or the
publisher's last success and last error.

## AI Agent Context

Agent-facing content is layered so each piece is loaded only when it is relevant:

| Layer                             | Loaded                      | Contains                                          |
| --------------------------------- | --------------------------- | ------------------------------------------------- |
| `AGENTS.md`                       | always                      | project identity, workflow rules, validation loop |
| `.agents/instructions/*.md`       | per touched file            | passive style rules for one file type             |
| `.agents/skills/*/SKILL.md`       | when a task matches         | active procedures for a specific kind of work     |
| `docs/development/`, `docs/user/` | when a human or agent reads | explanations, decisions, guides — this document   |

The skill catalogue and the symlink layout that makes one directory work for every agent vendor are documented in
[`.agents/skills/README.md`](../../.agents/skills/README.md). For working with AI coding agents in this repository,
see [`AI_AGENTS.md`](./AI_AGENTS.md).

## Design decisions

See [DECISIONS.md](./DECISIONS.md).

## Testing

`tests/` runs against a mocked server (`AiohttpClientMocker`):

- `test_config_flow.py` covers the receive flow, reconfigure, reauth and options.
- `test_share.py` covers the share flow and the publisher.
- `test_entities.py` covers the mirrored entities.
- `conftest.py` holds one receive and one share config entry and the mocked server responses.

## Dependencies

No PyPI requirements: the client uses `aiohttp` and `yarl`, which Home Assistant ships. The minimum Home Assistant
version is in `hacs.json`.
