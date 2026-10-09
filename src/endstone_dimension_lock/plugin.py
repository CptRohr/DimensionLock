from __future__ import annotations

import time
from pathlib import Path

from endstone import Player
from endstone.command import Command, CommandSender
from endstone.level import Dimension, Location
from endstone.plugin import Plugin
from typing_extensions import override

from .state import clear_state, load_saved_state, merge_state, save_state


class DimensionLockPlugin(Plugin):
    prefix = "DimensionLock"
    api_version = "0.11"

    commands = {
        "dimensionlock": {
            "description": "Toggle Nether/End portal restrictions.",
            "usages": [
                "/dimensionlock nether [on|off]",
                "/dimensionlock end [on|off]",
                "/dimensionlock status",
                "/dimensionlock reset",
            ],
            "permissions": ["dimensionlock.command.dimensionlock"],
        }
    }

    permissions = {
        "dimensionlock.command.dimensionlock": {
            "description": "Allow operators to manage portal locking settings.",
            "default": "op",
        }
    }

    def __init__(self) -> None:  # type: ignore[misc]
        super().__init__()
        self._saved_overrides: dict[str, bool] = {}
        self._last_denial_log: dict[str, float] = {}
        self._safe_locations: dict[str, Location] = {}

    @override
    def on_enable(self) -> None:
        from .listener import DimensionLockListener

        self.save_default_config()
        self._saved_overrides = self._load_saved_overrides()
        self.register_events(DimensionLockListener(self))
        self.logger.info("DimensionLock enabled.")

    @override
    def on_disable(self) -> None:
        self.logger.info("DimensionLock disabled.")

    @override
    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if command.name != "dimensionlock":
            return True
        if not args:
            self._show_usage(sender)
            return False

        subcommand = args[0].lower()
        if subcommand == "status":
            self._show_status(sender)
            return True
        if subcommand == "reset":
            self._reset_state()
            sender.send_message("Dimension lock settings reset to config defaults.")
            return True
        if subcommand not in {"nether", "end"}:
            self._show_usage(sender)
            return False

        if len(args) != 2 or args[1].lower() not in {"on", "off"}:
            self._show_usage(sender)
            return False

        target = subcommand
        enabled = args[1].lower() == "on"
        self._set_dimension_lock(target, enabled)
        state = self.effective_state()
        dimension_label = "Nether" if target == "nether" else "End"
        status = "enabled" if state[f"{target}_locked"] else "disabled"
        sender.send_message(f"{dimension_label} dimension lock is now {status}.")
        return True

    def effective_state(self) -> dict[str, bool]:
        return merge_state(self.config, self._saved_overrides)

    def is_dimension_locked(self, dimension: Dimension) -> bool:
        state = self.effective_state()
        if dimension.type == Dimension.NETHER:
            return state.get("nether_locked", False)
        if dimension.type == Dimension.THE_END:
            return state.get("end_locked", False)
        return False

    def dimension_label(self, dimension: Dimension) -> str:
        if dimension.type == Dimension.NETHER:
            return "Nether"
        if dimension.type == Dimension.THE_END:
            return "End"
        if dimension.type == Dimension.OVERWORLD:
            return "Overworld"
        return str(dimension.name).replace("_", " ").title()

    def remember_safe_location(self, player: Player, location: Location | None = None) -> None:
        source = location if location is not None else player.location
        if self.is_dimension_locked(source.dimension):
            return

        self._safe_locations[str(player.unique_id)] = Location(
            source.dimension,
            source.x,
            source.y,
            source.z,
            pitch=source.pitch,
            yaw=source.yaw,
        )

    def forget_safe_location(self, player: Player) -> None:
        self._safe_locations.pop(str(player.unique_id), None)

    def return_player_to_safe_location(self, player: Player, destination: Dimension) -> None:
        player_key = str(player.unique_id)
        safe_location = self._safe_locations.get(player_key)
        dimension_name = self.dimension_label(destination)
        if safe_location is None or self.is_dimension_locked(safe_location.dimension):
            self.logger.warning(
                f"Could not return {player.name} from the {dimension_name}: "
                "no unlocked safe location is cached."
            )
            player.send_message(
                f"§cTravel to the {dimension_name} is disabled, but no safe return location is available."
            )
            return

        destination_type = destination.type

        def return_player() -> None:
            if not player.is_valid or player.dimension.type != destination_type:
                return

            if not player.teleport(safe_location):
                self.logger.error(
                    f"Failed to return {player.name} from the {dimension_name} to their last safe location."
                )
                return

            deny_message = self.config.get(
                "deny_message",
                "§cTravel to the {dimension} is currently disabled.",
            )
            player.send_message(deny_message.format(dimension=dimension_name))
            self.log_denied_attempt(player, dimension_name)

        self.server.scheduler.run_task(self, return_player, delay=1)

    def log_denied_attempt(self, player: Player, dimension_name: str) -> None:
        config_log_enabled = bool(self.config.get("log_denied_attempts", True))
        if not config_log_enabled:
            return

        now = time.monotonic()
        last_logged = self._last_denial_log.get(player.name, 0.0)
        if now - last_logged >= 10.0:
            self.logger.warning(f"Denied {player.name} from entering the {dimension_name}.")
            self._last_denial_log[player.name] = now

    def _show_usage(self, sender: CommandSender) -> None:
        sender.send_error_message("Usage: /dimensionlock <nether|end|status|reset> [on|off]")

    def _show_status(self, sender: CommandSender) -> None:
        state = self.effective_state()
        sender.send_message(
            f"Dimension lock status: Nether={self._state_label(state.get('nether_locked', False))}, "
            f"End={self._state_label(state.get('end_locked', False))}"
        )

    def _state_label(self, locked: bool) -> str:
        return "locked" if locked else "unlocked"

    def _load_saved_overrides(self) -> dict[str, bool]:
        path = self._state_path()
        if not path.exists():
            return {}
        try:
            loaded = load_saved_state(path)
        except (TypeError, ValueError):
            self.logger.warning(f"Ignoring malformed dimension lock state in {path}.")
            return {}
        if not loaded:
            self.logger.warning(f"Dimension lock state file {path} was empty or invalid; using config defaults.")
            return {}
        self.logger.info("Loaded saved dimension lock overrides.")
        return loaded

    def _state_path(self) -> Path:
        return Path(str(self.data_folder)) / "state.json"

    def _set_dimension_lock(self, dimension: str, enabled: bool) -> None:
        key = f"{dimension}_locked"
        self._saved_overrides[key] = enabled
        save_state(self._state_path(), self._saved_overrides)

    def _reset_state(self) -> None:
        self._saved_overrides = {}
        clear_state(self._state_path())
        self.logger.info("Dimension lock overrides cleared; config defaults restored.")

__all__ = ["DimensionLockPlugin"]
