# Scan Worker Tests

## Purpose
Tests verifying concurrent scan tasks, Redis token expiration locks, and state machine transitions.

## Files
- `test_scan_isolation.py`: Verifies isolation and non-interference across concurrent scans.
- `test_scan_redis_integration.py`: Validates Redis Lua scripts, state decrementing, and TTL behaviors.
