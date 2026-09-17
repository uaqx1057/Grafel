# Grafel Product Evolution Plan

Last updated: 2026-07-09

## Goal

Push Grafel from "clean refactored local tool" toward a sturdier desktop product by:

1. slimming the Tk shell further
2. making watch/session behavior more deterministic to verify
3. hardening the build and release path

## Implementation tracks

### 1. Runtime extraction

- `grafel_core/watch_runtime.py`
  - watch process launch config
  - watch start-plan UI hints
  - watch line classification mapping
  - watch exit-state evaluation

- `grafel_core/meter_runtime.py`
  - initial meter state resolution
  - unscoped fallback messaging
  - Copilot event accumulation
  - Copilot "ready to print" decisions
  - Claude prompt summary math
  - baseline update rules

### 2. Deterministic integration harness

- `tests/integration_harness.py`
  - temp repo generator
  - temp workspace generator
  - fake process fixture

- use harness-backed tests for:
  - watch runtime decisions
  - meter runtime decisions
  - release/version helpers

### 3. Release hardening

- `grafel_core/release.py`
  - app version extraction
  - Inno Setup detection
  - installer command generation
  - release preflight checks

- `build.bat`
  - verify first
  - clean stale artifacts
  - build from `Grafel.spec`
  - derive installer version from `APP_VERSION`

## Current limitations

- real `graphify watch` is still not fully deterministic enough for a strict always-on smoke test
- `grafel.py` still contains significant monitor orchestration and UI rendering logic
- packaging is much cleaner now, but still depends on local Windows tooling availability

## Near-term next steps

1. integrate `watch_runtime.py` into watch start/stop paths
2. integrate `meter_runtime.py` into Copilot and Claude live-meter loops
3. add release preflight tests and optional build preflight command
4. keep broadening smoke coverage where external tooling is stable enough
