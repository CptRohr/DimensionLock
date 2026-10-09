import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from endstone.event import Event, PlayerDimensionChangeEvent, PlayerPortalEvent

from endstone_dimension_lock.listener import DimensionLockListener
from endstone_dimension_lock.plugin import DimensionLockPlugin
from endstone_dimension_lock.state import default_state_from_config, merge_state, save_state


class FakePlayer:
    def __init__(self, name: str = "Alice") -> None:
        self.name = name
        self.unique_id = name
        self.dimension = FakeDimension("Dimension.Type.OVERWORLD")
        self.is_valid = True
        self.messages: list[str] = []
        self.teleport_targets: list["FakeLocation"] = []

    def send_message(self, message: str) -> None:
        self.messages.append(message)

    def teleport(self, location: "FakeLocation") -> bool:
        self.teleport_targets.append(location)
        self.dimension = location.dimension
        return True


class FakeDimension:
    def __init__(self, dimension_type: object) -> None:
        self.type = dimension_type
        self.name = str(dimension_type)


class FakeLocation:
    def __init__(
        self,
        dimension_type: object,
        x: float = 12.5,
        y: float = 70.0,
        z: float = -4.5,
        pitch: float = 2.0,
        yaw: float = 90.0,
    ) -> None:
        self.dimension = dimension_type if isinstance(dimension_type, FakeDimension) else FakeDimension(dimension_type)
        self.x = x
        self.y = y
        self.z = z
        self.pitch = pitch
        self.yaw = yaw


class FakePortalEvent:
    def __init__(self, dimension_type: object, player: FakePlayer) -> None:
        self.player = player
        self.to_location = FakeLocation(dimension_type)
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeDimensionChangeEvent:
    def __init__(self, dimension_type: object, player: FakePlayer) -> None:
        self.player = player
        self.to_dimension = FakeDimension(dimension_type)


class FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


class FakeScheduler:
    def __init__(self) -> None:
        self.tasks: list[tuple[object, int]] = []
        self.plugins: list[object] = []

    def run_task(self, plugin: object, task: object, delay: int = 0) -> None:
        self.plugins.append(plugin)
        self.tasks.append((task, delay))


class FakePlugin:
    def __init__(self, state: dict[str, bool] | None = None) -> None:
        self.config = {
            "nether_locked": False,
            "end_locked": False,
            "log_denied_attempts": True,
            "deny_message": "§cTravel to the {dimension} is currently disabled.",
        }
        self._state = state or {}
        self.remembered_locations: list[tuple[FakePlayer, FakeLocation]] = []
        self.return_requests: list[tuple[FakePlayer, FakeDimension]] = []
        self._safe_locations: dict[str, FakeLocation] = {}
        self._last_denial_log: dict[str, float] = {}
        self.forgotten_players: list[FakePlayer] = []
        self.denied_attempts: list[tuple[FakePlayer, str]] = []
        self.logger = FakeLogger()
        self.scheduler = FakeScheduler()
        self.server = type("Server", (), {"scheduler": self.scheduler})()

    def is_dimension_locked(self, dimension: FakeDimension) -> bool:
        if str(dimension.type) == "Dimension.Type.NETHER":
            return self._state.get("nether_locked", False)
        if str(dimension.type) == "Dimension.Type.THE_END":
            return self._state.get("end_locked", False)
        return False

    def dimension_label(self, dimension: FakeDimension) -> str:
        if str(dimension.type) == "Dimension.Type.NETHER":
            return "Nether"
        if str(dimension.type) == "Dimension.Type.THE_END":
            return "End"
        return "Overworld"

    def remember_safe_location(self, player: FakePlayer, location: FakeLocation | None = None) -> None:
        if location is not None:
            self.remembered_locations.append((player, location))

    def forget_safe_location(self, player: FakePlayer) -> None:
        self.forgotten_players.append(player)

    def return_player_to_safe_location(self, player: FakePlayer, destination: FakeDimension) -> None:
        self.return_requests.append((player, destination))

    def log_denied_attempt(self, player: FakePlayer, dimension_name: str) -> None:
        self.denied_attempts.append((player, dimension_name))


class DimensionLockTests(unittest.TestCase):
    def test_portal_handler_has_runtime_event_class_annotation(self) -> None:
        annotation = inspect.signature(DimensionLockListener.on_player_portal).parameters["event"].annotation

        self.assertIs(annotation, PlayerPortalEvent)
        self.assertTrue(issubclass(annotation, Event))

    def test_dimension_change_handler_has_runtime_event_class_annotation(self) -> None:
        annotation = inspect.signature(DimensionLockListener.on_player_dimension_change).parameters["event"].annotation

        self.assertIs(annotation, PlayerDimensionChangeEvent)
        self.assertTrue(issubclass(annotation, Event))

    def test_locked_dimension_change_requests_return_to_safe_location(self) -> None:
        plugin = FakePlugin({"nether_locked": True})
        listener = DimensionLockListener(plugin)
        player = FakePlayer()
        event = FakeDimensionChangeEvent("Dimension.Type.NETHER", player)

        listener.on_player_dimension_change(event)

        self.assertEqual(plugin.return_requests, [(player, event.to_dimension)])

    def test_unlocked_dimension_change_is_allowed(self) -> None:
        plugin = FakePlugin({"nether_locked": False})
        listener = DimensionLockListener(plugin)
        player = FakePlayer()
        event = FakeDimensionChangeEvent("Dimension.Type.NETHER", player)

        listener.on_player_dimension_change(event)

        self.assertEqual(plugin.return_requests, [])

    def test_move_handler_remembers_pre_move_location(self) -> None:
        plugin = FakePlugin()
        listener = DimensionLockListener(plugin)
        player = FakePlayer()
        location = FakeLocation("Dimension.Type.OVERWORLD")
        event = type("FakeMoveEvent", (), {"player": player, "from_location": location})()

        listener.on_player_move(event)

        self.assertEqual(plugin.remembered_locations, [(player, location)])

    def test_safe_location_is_copied_only_from_unlocked_dimension(self) -> None:
        plugin = FakePlugin()
        player = FakePlayer()
        safe_location = FakeLocation("Dimension.Type.OVERWORLD")
        plugin._safe_locations = {}

        with patch(
            "endstone_dimension_lock.plugin.Location",
            side_effect=lambda dimension, x, y, z, pitch, yaw: FakeLocation(
                dimension, x, y, z, pitch, yaw
            ),
        ):
            DimensionLockPlugin.remember_safe_location(plugin, player, safe_location)
            copied = plugin._safe_locations[player.unique_id]
            self.assertIsNot(copied, safe_location)
            self.assertEqual((copied.x, copied.y, copied.z), (12.5, 70.0, -4.5))
            self.assertEqual((copied.pitch, copied.yaw), (2.0, 90.0))

            plugin._state["nether_locked"] = True
            DimensionLockPlugin.remember_safe_location(
                plugin,
                player,
                FakeLocation("Dimension.Type.NETHER"),
            )

        self.assertIs(plugin._safe_locations[player.unique_id], copied)

    def test_missing_safe_location_reports_failure_without_scheduling(self) -> None:
        plugin = FakePlugin({"nether_locked": True})
        player = FakePlayer()
        destination = FakeDimension("Dimension.Type.NETHER")

        DimensionLockPlugin.return_player_to_safe_location(plugin, player, destination)

        self.assertEqual(plugin.scheduler.tasks, [])
        self.assertIn("no safe return location", player.messages[0].lower())

    def test_cached_safe_location_is_used_and_rollback_does_not_loop(self) -> None:
        plugin = FakePlugin({"nether_locked": True})
        player = FakePlayer()
        destination = FakeDimension("Dimension.Type.NETHER")
        safe_location = FakeLocation("Dimension.Type.OVERWORLD")
        plugin._safe_locations[player.unique_id] = safe_location

        DimensionLockPlugin.return_player_to_safe_location(plugin, player, destination)

        self.assertEqual(len(plugin.scheduler.tasks), 1)
        task, delay = plugin.scheduler.tasks[0]
        self.assertEqual(delay, 1)
        player.dimension = destination
        task()

        self.assertEqual(player.teleport_targets, [safe_location])
        self.assertIs(player.dimension, safe_location.dimension)

        listener = DimensionLockListener(plugin)
        listener.on_player_dimension_change(
            FakeDimensionChangeEvent("Dimension.Type.OVERWORLD", player)
        )
        self.assertEqual(len(plugin.scheduler.tasks), 1)

    def test_portal_event_is_cancelled_when_destination_is_locked(self) -> None:
        plugin = FakePlugin({"nether_locked": True})
        listener = DimensionLockListener(plugin)
        player = FakePlayer()
        event = FakePortalEvent("Dimension.Type.NETHER", player)

        listener.on_player_portal(event)

        self.assertTrue(event.cancelled)
        self.assertEqual(player.messages, ["§cTravel to the Nether is currently disabled."])

    def test_portal_event_is_not_cancelled_when_destination_is_unlocked(self) -> None:
        plugin = FakePlugin({"nether_locked": False})
        listener = DimensionLockListener(plugin)
        player = FakePlayer()
        event = FakePortalEvent("Dimension.Type.NETHER", player)

        listener.on_player_portal(event)

        self.assertFalse(event.cancelled)
        self.assertEqual(player.messages, [])

    def test_independent_toggles_are_merged(self) -> None:
        base = {"nether_locked": True, "end_locked": False}
        overrides = {"end_locked": True}
        merged = merge_state(base, overrides)

        self.assertTrue(merged["nether_locked"])
        self.assertTrue(merged["end_locked"])

    def test_default_state_loads_without_saved_state(self) -> None:
        config = {"nether_locked": False, "end_locked": False}
        default_state = default_state_from_config(config)

        self.assertEqual(default_state, {"nether_locked": False, "end_locked": False})

    def test_state_file_persists_and_uses_boolean_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            save_state(state_path, {"nether_locked": True, "end_locked": False})

            self.assertTrue(state_path.exists())
            self.assertIn('"nether_locked":true', state_path.read_text(encoding='utf-8'))


if __name__ == "__main__":
    unittest.main()
