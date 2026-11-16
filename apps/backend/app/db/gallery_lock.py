"""Serialize gallery snapshots with publishing for one event, for this transaction."""
def lock_gallery(conn, event_id):
    conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (str(event_id),))
