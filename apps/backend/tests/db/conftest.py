"""Backfill must be exercised on the fresh database before other tests migrate it."""


def pytest_collection_modifyitems(items):
    items.sort(key=lambda item: 0 if item.name == 'test_lookup_backfill_triggers_and_default_privileges' else 1)
