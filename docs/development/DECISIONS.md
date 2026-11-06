# Architectural and Design Decisions

This document records significant architectural and design decisions made during the development of this integration.

## Format

Each decision is documented with:

- **Date:** When the decision was made
- **Context:** Why this decision was necessary
- **Decision:** What was decided
- **Rationale:** Why this approach was chosen
- **Consequences:** Expected impacts and trade-offs

> [!NOTE]
> Guidance on _when_ a decision is worth recording here, and a copy-ready entry template, lives in the
> [`ha-planning`](../../.agents/skills/ha-planning/SKILL.md) agent skill.

The entries below were written down on 2026-11-06 from the code as it stood at version 0.1.0; the decisions
themselves were made while that code was written.

---

## Decision Log

### Own API client instead of a library

**Date:** 2026-11-06 (recorded)

**Context:** The integration talks to the Hofmätteli Telemetry server, a small FastAPI service with three endpoints
and bearer tokens.

**Decision:** Write the client in `api/client.py` on `aiohttp`, with no PyPI requirement.

**Rationale:**

- No library for this server exists, and three endpoints do not justify publishing one
- `aiohttp` and `yarl` ship with Home Assistant, so the integration installs nothing
- The client maps status codes straight to the exceptions the coordinator and publisher need

**Consequences:**

- A server API change means changing `api/client.py` and its tests here
- The server and this integration have to be kept compatible by hand; there is no shared schema

---

### One integration, two modes per config entry

**Date:** 2026-11-06 (recorded)

**Context:** Sending entities to the server and showing entities from it are both needed, often on different
Home Assistant installations, sometimes on the same one.

**Decision:** One integration whose config flow starts with a menu. The choice is stored as `mode` (`share` or
`receive`) in the entry data, and setup branches on it.

**Rationale:**

- Users install and find one integration, with the same URL, token and SSL handling for both directions
- The API client, validation and reauth are shared
- Two entries cover a Home Assistant that does both

**Consequences:**

- `__init__.py`, the options flow, reconfigure and diagnostics all branch on the mode
- `entry.runtime_data` has an optional coordinator and an optional publisher; exactly one is set

---

### Receive: one coordinator request for all entities, every minute

**Date:** 2026-11-06 (recorded)

**Context:** The server only answers requests; it cannot notify a receiver.

**Decision:** A `DataUpdateCoordinator` fetches `GET /entities?full=true` every 60 seconds, and every mirrored
entity reads its own entry from the result.

**Rationale:**

- One request per minute regardless of how many entities are selected, which keeps the server and any reverse proxy
  rate limit happy
- Failures map onto Home Assistant's standard handling: `ConfigEntryAuthFailed` for reauth, `UpdateFailed` with a
  bounded `retry_after` for rate limits

**Consequences:**

- Received values lag the sender by up to a minute
- The whole remote entity list is transferred each time, including entities nobody selected

---

### Share: event-driven publisher instead of a coordinator

**Date:** 2026-11-06 (recorded)

**Context:** Sharing is the opposite direction: local changes must reach the server, and a busy sensor must not
flood it.

**Decision:** `coordinator/publisher.py` listens to state changes of the selected entities and pushes through a
single drain task, one `PUT` at a time, keeping only the newest pending state per entity. It also pushes everything
once at start and every 4 hours. `unknown` and `unavailable` are never sent. A failed push is dropped, not retried.

**Rationale:**

- A coordinator polls on an interval; sharing is triggered by changes
- One request at a time with coalescing bounds the load whatever the sensors do
- The heartbeat keeps a sensor that never changes from looking stale on the receiving side
- Skipping `unknown` / `unavailable` stops a restart from overwriting the last good value
- Retrying a failed push would send an outdated state; the next change or heartbeat sends a current one

**Consequences:**

- The publisher handles its own failures: reauth on a rejected token, waiting on a rate limit, logging once on other
  errors
- After an outage, an unchanged entity reaches the server only at the next heartbeat (at most 4 hours)

---

### The server's receive time decides freshness

**Date:** 2026-11-06 (recorded)

**Context:** The server flags an entity as `stale` when its timestamp is too old (5 hours by default). The older YAML
automation sent the entity's `last_changed`, so a sensor that never changed looked stale even while pushed.

**Decision:** The publisher does not send `last_changed`; the server stamps each value when it receives it.

**Rationale:**

- Combined with the 4-hour heartbeat, `stale` then means "the sender is gone", which is what a receiver wants to
  know

**Consequences:**

- Installations still pushing with the old YAML automation show unchanged sensors as stale (documented in the README)

---

### Unique IDs from the entry ID and the remote entity ID

**Date:** 2026-11-06 (recorded)

**Context:** Mirrored entities need stable unique IDs. The server has no serial number or account ID, and its URL
must not be a unique ID.

**Decision:** Unique ID is `{entry_id}_{remote_entity_id}`; the receive device is identified by the entry ID.

**Rationale:**

- The entry ID is stable for the life of the entry, survives a URL change through reconfigure, and is unique
- The remote entity ID is unique per server

**Consequences:**

- Removing and re-adding the integration creates new unique IDs; entity history does not carry over

---

### Entity metadata comes from the sender at runtime

**Date:** 2026-11-06 (recorded)

**Context:** The project rule is `EntityDescription` plus `translation_key`. Here the entities are not known in
advance; they are whatever the sender shares.

**Decision:** The name is the remote friendly name. Unit, device class and state class are read from the remote
attributes on every update, the name and icon when the entity is set up. Remote `binary_sensor.*` entities become binary sensors, everything else a sensor.

**Rationale:**

- A name the source supplies is the documented exception to translated names
- A shared temperature becomes a real temperature sensor with history and long-term statistics

**Consequences:**

- Device or state classes Home Assistant does not know are ignored
- A sender changing a unit changes the receiver's unit, with the usual statistics warnings

---

### Device named after the server host

**Date:** 2026-11-06

**Context:** The device took its name from the entry title, so titling the receive entry "Receiving from …" to match
"Sharing to …" would also have changed the device name and every new entity ID derived from it.

**Decision:** The device name is the host of the server URL; the entry title is independent of it.

**Rationale:**

- Entity IDs stay `sensor.<host>_<name>`, as documented in the README
- Renaming the entry no longer has side effects on the device

**Consequences:**

- After a reconfigure to a different host, the device name follows the new host (unless the user renamed the device)

---

## Future Considerations

### Push to the receiver

**Status:** Not possible with the current server

Received values lag by up to a minute because the server cannot notify receivers. A server-side WebSocket or
server-sent events endpoint would allow push; until then, polling stays.

### Restoring received values across restarts

**Status:** Not implemented

Received entities are unavailable until the first successful poll after a restart. Restoring the last value would
help when the server is down while Home Assistant starts.

---

## Decision Review

These decisions should be reviewed when the server API changes or major features are added.
