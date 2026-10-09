# Endstone Plugin Development Guide

This repository contains a small Endstone 0.11 plugin that locks Nether/End entry while leaving the Overworld available.

## Base project conventions
- Build with `uv` and `hatchling`.
- Keep the package name as `endstone_dimension_lock` and the plugin entry point as `dimension-lock`.
- Set `api_version = "0.11"` on the plugin class.
- Use the Endstone `@event_handler` pattern and `self.register_events(...)` for event listeners.
- Keep commands in the plugin class with explicit permission defaults and usage strings.
- Keep event parameter annotations as runtime classes; Endstone inspects them when registering listeners.

## Checked API facts
- `PlayerPortalEvent` is cancellable in Endstone 0.11 and exposes `from_location` and `to_location`.
- `PlayerDimensionChangeEvent` exists, but is not cancellable and exposes dimensions rather than prior coordinates.
- The plugin cancels portal entry before travel and uses a best-effort post-transition rollback for other cross-dimension teleports, based on cached safe locations. Brief arrival can occur; live server behavior must not be claimed as tested without performing it.

## Validation
Run the following before shipping:

```powershell
uv sync --extra dev
uv run ruff check src/ tests/
uv run python -m unittest discover -s tests
uv build
```
