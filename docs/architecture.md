# VigilantCore Platform Architecture

VigilantCore is evolving from a single-node event monitor into the coordinating
**centerpiece for emergency action** — a system that monitors adverse events,
reacts with or without internet and grid power, communicates over whatever links
are available (LoRa/Meshtastic mesh, satellite, BLE, MQTT/LAN), informs other
systems and responders, and uses local AI to fuse and prioritize.

This document describes the **plugin kernel** that makes that possible. It was
introduced in Phase 1 (architecture & contracts) and is the foundation every
later capability builds on. It is fully backward compatible: with no plugins
configured, VigilantCore behaves exactly as before.

## The big picture

```
                         vigilant-core (Python hub)
  ┌──────────────────────────────────────────────────────────────────────┐
  │  INGEST            FUSION / AI            ROUTING            EGRESS     │
  │  source plugins →  normalize → dedup  →   policy engine  →  transport  │
  │  (RSS, APIs,       → impact (Ollama)  →   (urgency, geo,    + device   │
  │   LoRa-in,           → AI fusion         channel, power)     plugins   │
  │   sensors,         EmergencyEvent      MultiChannelRouter   (LoRa-out, │
  │   MQTT-in)         (canonical, v2.0)   (Phase 2)            BLE, sat,   │
  │                          │                                  MQTT, UI,  │
  │                    SQLite store +                           siren)     │
  │                    store-and-forward (mesh)                            │
  └────────────┬─────────────────────────────────────────────┬───────────┘
               │ shared EmergencyEvent contract (JSON)        │
        ┌──────┴───────┐                              ┌────────┴────────┐
        │ edge/ daemons │ (Rust/Go, low-power)        │ sibling apps    │
        │ lora, mesh,   │  bridged via MQTT/stdio      │ via MQTT bus    │
        │ satellite,    │                              │                 │
        │ ble, power    │                              │                 │
        └───────────────┘                              └─────────────────┘
```

## Components

### The contract — `contracts/`

`contracts.EmergencyEvent` is the single shape every component agrees on. It is a
strict superset of the v1.0 normalized alert produced by
`utils.event_normalization.normalize_event_payload`, so existing alerts upgrade
losslessly (`EmergencyEvent.from_normalized`). New platform fields — a stable
`event_id` (ULID), `origin_node_id`, `hazard_type`, `trust` tier, mesh
`ttl_hops`/`seen_nodes`, and recommended `actions` — enable cross-node
propagation, routing, and trust decisions. See
[emergency-event-schema.md](emergency-event-schema.md).

The contract is the boundary that lets the Rust/Go edge daemons (Phase 2) and
sibling apps interoperate without sharing Python code: they exchange
schema-valid JSON over MQTT/stdio.

### The plugin kernel — `plugins/`

Every capability is a plugin of one of four kinds (`plugins/base.py`):

| Kind | Base class | Contract method | Examples |
|------|-----------|-----------------|----------|
| Source | `SourcePlugin` | `async poll(ctx) -> List[EmergencyEvent]` | RSS, sensors, LoRa-in, MQTT-in |
| Transport | `TransportPlugin` | `send(event)` (+ inbound to bus) | MQTT, LoRa/Meshtastic, BLE, satellite |
| Device | `DevicePlugin` | `render(event)` | siren, display, GPIO relay, notification |
| Sink | `SinkPlugin` | `handle(event)` | webhook, shell action, digest, export |

Plugins communicate through an in-process **`EventBus`** (publish/subscribe),
which replaces the engine's single `on_new_alert` callback. Topics:

- `event.new` — every newly stored alert (transports + sinks subscribe).
- `event.high` — high-priority only: severity high/critical OR `impact_score >= 7`
  (devices like sirens default to this).
- `event.ingest` — inbound events from transports re-entering the pipeline.

Every plugin reports health in the same shape as the v0.8.0 source-health
telemetry (`PluginHealth`: attempts, successes, errors, latency), so the
dashboard can show all of them uniformly.

### Lifecycle — `plugins/loader.py` + `plugins/registry.py`

Plugins are declared in config (`AppConfig.plugins`) and loaded by `build_registry`:

```json
{
  "plugins": [
    {"type": "rss_source", "name": "county-rss", "enabled": true,
     "options": {"feeds": ["https://example.gov/alerts.rss"]}},
    {"type": "mqtt_transport", "name": "bus", "enabled": true,
     "options": {"host": "127.0.0.1", "base_topic": "intel/events"}},
    {"type": "notify_device", "name": "siren", "enabled": true, "options": {}}
  ]
}
```

`type` resolves to a built-in plugin or a `"module:ClassName"` path for
out-of-tree plugins. The registry starts each plugin, wires egress plugins to bus
topics, polls sources each cycle, and fans stored events out to egress.

### Mesh node identity + store-and-forward — `mesh/` (a later release)

The `mesh/` package below lands in a subsequent release; the kernel and contract
in this release are what it builds on.

- `mesh/node.py` — a persistent `node_id` (ULID), label, and role
  (`hub`/`edge`/`relay`) under the platform data dir, so events can record their
  origin and travel path.
- `mesh/forwarding.py` — a SQLite-backed store-and-forward queue implementing
  **gossip / flood-with-suppression**: duplicate `event_id`s and looped events
  (this node already in `seen_nodes`) are suppressed; otherwise the node stamps
  itself and enqueues a hop-decremented copy. `ttl_hops` bounds flooding (mesh
  storm protection). The queue survives power loss because it is persisted.

Phase 1 ships the model + reference algorithm; Phase 2's radios drive it.

## How the engine uses it

A later release wires this kernel into `engine/monitor.py` (`MonitorEngine`) as a
platform layer that degrades gracefully — if an optional plugin/transport
dependency is missing, monitoring still runs. Until then the kernel is
self-contained and driven directly (`build_registry(config)` +
`registry.publish(event)`); the wiring will be:

1. **Ingest** — `gather_items()` additionally pulls `registry.poll_sources()`
   and any buffered inbound transport events, feeding them through the same
   dedup/location pipeline as native fetchers.
2. **Egress** — when `process_items()` stores a new alert, it builds an
   `EmergencyEvent`, offers it to the store-and-forward queue, and publishes it
   to the bus, where transports/devices/sinks react.

## Roadmap

Phase 1 ships, across its releases, the contract, this plugin kernel with three
reference plugins (RSS source, MQTT transport, notify device), and the mesh
node/forwarding model (a later release). Subsequent phases —
multi-channel routing, LoRa/BLE/satellite transports + Rust/Go edge daemons,
encrypted offline storage, LLM gateway, AI fusion, prompt-injection hardening,
event signing — each land as plugins or additive modules against this contract.
See the project plan and the issue tracker (#12/#19/#40, #25–#29, #33/#34, #42,
#35, #36, #37, #39, #57–#60, #67, #70).
