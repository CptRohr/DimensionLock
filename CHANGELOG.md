# Changelog

## Unreleased

- Added independent Nether and End locking with operator-only commands.
- Added persistent command overrides, config defaults, and reset handling.
- Cancelled portal travel into locked dimensions and added a best-effort post-transition rollback for direct cross-dimension teleports.
- Documented that direct-teleport rollback may allow brief arrival and requires live-server verification.
