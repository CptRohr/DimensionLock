from endstone.event import (
    PlayerDimensionChangeEvent,
    PlayerJoinEvent,
    PlayerMoveEvent,
    PlayerPortalEvent,
    PlayerQuitEvent,
    event_handler,
)

from .plugin import DimensionLockPlugin


class DimensionLockListener:
    def __init__(self, plugin: DimensionLockPlugin) -> None:
        self._plugin = plugin

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent) -> None:
        self._plugin.remember_safe_location(event.player)

    @event_handler
    def on_player_move(self, event: PlayerMoveEvent) -> None:
        self._plugin.remember_safe_location(event.player, event.from_location)

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent) -> None:
        self._plugin.forget_safe_location(event.player)

    @event_handler
    def on_player_portal(self, event: PlayerPortalEvent) -> None:
        destination = event.to_location.dimension
        if not self._plugin.is_dimension_locked(destination):
            return

        player = event.player
        dimension_name = self._plugin.dimension_label(destination)
        message = self._plugin.config.get("deny_message", "§cTravel to the {dimension} is currently disabled.")
        player.send_message(message.format(dimension=dimension_name))
        self._plugin.log_denied_attempt(player, dimension_name)
        event.cancel()

    @event_handler
    def on_player_dimension_change(self, event: PlayerDimensionChangeEvent) -> None:
        destination = event.to_dimension
        if self._plugin.is_dimension_locked(destination):
            self._plugin.return_player_to_safe_location(event.player, destination)
