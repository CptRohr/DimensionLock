# Endstone Dimension Lock

An Endstone 0.11 plugin for controlling access to the Nether and the End. The two dimensions are configured independently; the Overworld is never locked.

## Features

- Cancel vanilla portal travel into a locked Nether or End.
- Best-effort rollback when a player is moved into a locked dimension through a direct cross-dimension teleport.
- Persist command changes across restarts and reset to configured defaults.
- No recurring tasks or third-party runtime dependencies beyond Endstone and `typing_extensions`.

## Installation

1. Download the `endstone_dimension_lock-*.whl` file from a release, or build it as described below.
2. Copy the wheel into the Endstone server's `plugins/` directory.
3. Restart the server.
4. Use `/dimensionlock status` to inspect current settings.

## Commands

```text
/dimensionlock nether on
/dimensionlock nether off
/dimensionlock end on
/dimensionlock end off
/dimensionlock status
/dimensionlock reset
```

The command works from the server console and authorized in-game operators. Its permission, `dimensionlock.command.dimensionlock`, defaults to operators only.

## Configuration

On first run, Endstone copies the package's `config.toml` into the plugin data folder. These values provide the defaults:

```toml
nether_locked = false
end_locked = false
log_denied_attempts = true
deny_message = "§cTravel to the {dimension} is currently disabled."
```

`{dimension}` is replaced with `Nether` or `End`.

Command overrides are saved in `state.json` under the plugin data folder. Writes use a temporary file followed by replacement. `/dimensionlock reset` removes the saved overrides and restores the values from `config.toml`. Invalid or missing state data falls back to config defaults.

## Enforcement and limitations

### Portal travel

The plugin uses Endstone's cancellable `PlayerPortalEvent` and checks the destination dimension. Entry into a locked dimension is cancelled before travel; travel to the Overworld and exit from a locked dimension are allowed.

### Direct teleports and UTP

Endstone 0.11's `PlayerDimensionChangeEvent` is not cancellable and contains dimension information, not the previous coordinates. For a direct cross-dimension teleport, the plugin therefore saves a copy of each player's recent location in an unlocked dimension and schedules a one-shot return if the player arrives in a locked dimension.

This is a **post-transition rollback**, not a pre-transition block: the player may briefly arrive in the destination dimension before being returned. If no unlocked location was cached, the plugin reports that it cannot safely return the player rather than guessing a location. Another plugin may also display its own teleport-success message before the rollback occurs.

UTP's home, warp, back, and cross-dimension TPA paths use player teleports and are intended to be covered by this fallback. UTP's TPR uses `spreadplayers` in the Overworld and does not transfer between dimensions. These paths were identified by inspecting the [UTP source](https://github.com/U-Blocks/UTP); this behavior has **not been integration-tested on a live Endstone server with UTP**. Test it on a copy of your world before relying on it.

The fallback is not a universal restriction on every plugin or server-side dimension transition. For a true pre-transition denial in UTP, UTP itself would need to check the destination before calling teleport.

## Build and checks

Requirements: Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --extra dev
uv run ruff check src/ tests/
uv run python -m unittest discover -s tests
uv build
```

The wheel is written to `dist/`. Unit tests use test doubles; they do not substitute for a live Endstone/BDS test.

## License

Distributed under the MIT License. See [LICENSE](LICENSE).
