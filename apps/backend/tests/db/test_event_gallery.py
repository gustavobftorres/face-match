import os
from io import BytesIO
from PIL import Image
from uuid import uuid4
import numpy as np
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import event_gallery as api
from app.api.app_session import authenticated, digest
from app.core.config import settings
from app.db.migrate import migrate
from app.db.provision_context import provision
from app.workers import gallery_tasks as worker

ADMIN, RUNTIME = os.getenv('TEST_DATABASE_ADMIN_URL'), os.getenv('TEST_DATABASE_RUNTIME_URL')
pytestmark = pytest.mark.skipif(not ADMIN or not RUNTIME, reason='disposable PostgreSQL URLs not configured')


def test_gallery_isolation_and_worker_validation(monkeypatch):
    migrate(ADMIN)
    with psycopg.connect(RUNTIME) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    provision(ADMIN, role)
    monkeypatch.setattr(settings, 'DATABASE_URL', RUNTIME)
    a, b, event_a, event_b, admin, person, outsider = (uuid4() for _ in range(7))
    with psycopg.connect(ADMIN) as conn:
        for tid in (a, b):
            conn.execute("INSERT INTO tenants (id,name,slug) VALUES (%s,'T',%s)", (tid, str(tid)))
        for uid in (admin, person, outsider):
            conn.execute('INSERT INTO users (id,google_subject) VALUES (%s,%s)', (uid, str(uid)))
        for eid, tid in ((event_a, a), (event_b, b)):
            conn.execute("INSERT INTO events (id,tenant_id,name,slug,status) VALUES (%s,%s,'E','event','published')", (eid, tid))
        conn.execute("INSERT INTO tenant_memberships VALUES (%s,%s,'owner')", (a, admin))
        conn.execute('INSERT INTO event_participations (tenant_id,event_id,user_id) VALUES (%s,%s,%s)', (a, event_a, person))
    monkeypatch.setattr(worker, 'list_gallery_folder', lambda folder: ('folder', [{'id':'file-id'}]))
    monkeypatch.setattr(worker, 'download_image', lambda file_id: b'data')
    monkeypatch.setattr(worker, 'process_image', lambda data: (b'jpeg', [[0.0]*128]))
    monkeypatch.setattr(api, 'extract_selfie', lambda data: [np.zeros(128)])
    scheduled = []
    monkeypatch.setattr(api.index_event, 'delay', lambda *args: scheduled.append(args))
    app = FastAPI()
    app.include_router(api.router)
    state = {'auth': (a, admin, digest('csrf'), 'session')}
    app.dependency_overrides[authenticated] = lambda: state['auth']
    c = TestClient(app, base_url='https://tenant.test', headers={'origin': 'https://tenant.test', 'x-csrf-token': 'csrf'})
    path = f'/events/{event_a}/gallery'
    state['auth'] = (a, person, digest('csrf'), 'session')
    assert c.post(path + '/index', json={'folder': 'abcdefghijk'}).status_code == 404
    assert c.get(path + '/jobs/latest').status_code == 404
    state['auth'] = (a, admin, digest('csrf'), 'session')
    assert c.post(path + '/index', headers={'x-csrf-token': 'bad'}, json={'folder':'abcdefghijk'}).status_code == 403
    assert c.get(path + '/jobs/latest').json() == {'job': None}
    response = c.post(path + '/index', json={'folder':'abcdefghijk'})
    assert response.status_code == 202
    job = response.json()['id']
    assert c.get(path + '/jobs/latest').json() == {'job': {'id': job, 'status': 'queued'}}
    assert c.post(path + '/index', json={'folder':'abcdefghijk'}).status_code == 409
    worker.index_event(str(b), str(event_b), job)
    assert c.get(path + f'/jobs/{job}').json()['status'] == 'queued'
    worker.index_event(*scheduled[0])
    assert c.get(path + f'/jobs/{job}').json()['status'] == 'ready'
    state['auth'] = (a, person, digest('csrf'), 'session')
    image = BytesIO()
    Image.new('RGB', (2, 2)).save(image, format='JPEG')
    result = c.post(path + '/search', files={'selfie': ('selfie.jpg', image.getvalue(), 'image/jpeg')})
    assert result.status_code == 200
    search, photo = result.json()['id'], result.json()['photos'][0]
    media = path + f'/searches/{search}/photos/{photo}'
    assert c.get(media).content == b'jpeg'
    with psycopg.connect(ADMIN) as conn:
        conn.execute('INSERT INTO event_participations (tenant_id,event_id,user_id) VALUES (%s,%s,%s)', (a, event_a, outsider))
    state['auth'] = (a, outsider, digest('csrf'), 'session')
    assert c.get(media).status_code == 404
    state['auth'] = (b, person, digest('csrf'), 'session')
    assert c.get(media).status_code == 404
    state['auth'] = (a, admin, digest('csrf'), 'session')
    assert c.get(media).status_code == 404
    with psycopg.connect(ADMIN) as conn:
        conn.execute('DELETE FROM event_participations WHERE tenant_id = %s AND event_id = %s AND user_id = %s', (a, event_a, person))
    state['auth'] = (a, person, digest('csrf'), 'session')
    assert c.get(media).status_code == 404
    # Search holds the lock until results commit; publication must wait.
    import threading
    with psycopg.connect(ADMIN) as conn:
        conn.execute('INSERT INTO event_participations (tenant_id,event_id,user_id) VALUES (%s,%s,%s)', (a,event_a,person))
        job2 = uuid4()
        conn.execute("INSERT INTO gallery_jobs (id,tenant_id,event_id,requested_by,folder_id,status) VALUES (%s,%s,%s,%s,'abcdefghijk','queued')", (job2,a,event_a,admin))
    original_lock = api.lock_gallery
    acquired, release, published = threading.Event(), threading.Event(), threading.Event()
    def paused_lock(conn, eid):
        original_lock(conn, eid)
        acquired.set()
        assert release.wait(5)
    monkeypatch.setattr(api, 'lock_gallery', paused_lock)
    results = []
    search_thread = threading.Thread(target=lambda: results.append(c.post(path + '/search', files={'selfie': ('selfie.jpg', image.getvalue(), 'image/jpeg')})))
    search_thread.start()
    assert acquired.wait(5)
    def publish():
        worker.index_event(str(a), str(event_a), str(job2))
        published.set()
    publish_thread = threading.Thread(target=publish)
    publish_thread.start()
    assert not published.wait(0.2)
    release.set()
    search_thread.join(5)
    publish_thread.join(5)
    assert published.is_set()
    assert results[0].status_code == 200


def test_recovery_lease_and_outbox(monkeypatch):
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from app.db.provision_gallery_dispatcher import provision as provision_dispatcher
    migrate(ADMIN)
    tid, eid, uid, jid, stale = (uuid4() for _ in range(5))
    relay = 'relay_' + uuid4().hex
    with psycopg.connect(ADMIN) as conn:
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(relay)))
        conn.execute("INSERT INTO tenants (id,name,slug) VALUES (%s,'T',%s)", (tid,str(tid)))
        conn.execute('INSERT INTO users (id,google_subject) VALUES (%s,%s)', (uid,str(uid)))
        conn.execute("INSERT INTO events (id,tenant_id,name,slug) VALUES (%s,%s,'E','event')", (eid,tid))
        conn.execute("INSERT INTO tenant_memberships VALUES (%s,%s,'owner')", (tid,uid))
        conn.execute("INSERT INTO gallery_jobs (id,tenant_id,event_id,requested_by,folder_id,status,created_at) VALUES (%s,%s,%s,%s,'abcdefghijk','queued',now()-interval '1 minute')", (jid,tid,eid,uid))
    provision_dispatcher(ADMIN, relay)
    monkeypatch.setattr(settings, 'DATABASE_URL', RUNTIME)
    monkeypatch.setattr(settings, 'GALLERY_DISPATCHER_DATABASE_URL', make_conninfo(RUNTIME, user=relay))
    messages = []
    monkeypatch.setattr(worker.index_event, 'delay', lambda *args: messages.append(args))
    worker.recover_pending()
    assert (str(tid),str(eid),str(jid)) in messages
    with psycopg.connect(ADMIN) as conn:
        conn.execute("UPDATE gallery_jobs SET status='processing', lease_token=%s, lease_until=now()-interval '1 second' WHERE id=%s", (stale,jid))
    messages.clear()
    worker.recover_pending()
    assert (str(tid),str(eid),str(jid)) in messages
    monkeypatch.setattr(worker, 'list_gallery_folder', lambda _: ('folder', []))
    worker.index_event(str(tid),str(eid),str(jid))
    worker.index_event(str(tid),str(eid),str(jid))
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute('SELECT status FROM gallery_jobs WHERE id=%s', (jid,)).fetchone() == ('ready',)
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(relay)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(relay)))


def test_selfie_dimensions_before_encoding(monkeypatch):
    from app.api.gallery_limit import GalleryUploadLimit
    from contextlib import contextmanager
    tid, uid = uuid4(), uuid4()
    app = FastAPI()
    app.add_middleware(GalleryUploadLimit)
    app.include_router(api.router, prefix='/api/v1')
    app.dependency_overrides[authenticated] = lambda: (tid, uid, digest('csrf'), 'session')
    monkeypatch.setattr(api, 'allowed', lambda *args: True)
    @contextmanager
    def session(*args):
        yield None
    monkeypatch.setattr(api, 'tenant_session', session)
    monkeypatch.setattr(api, 'extract_selfie', lambda _: pytest.fail('model must not run'))
    client = TestClient(app, base_url='https://tenant.test', headers={'origin':'https://tenant.test','x-csrf-token':'csrf'})
    data = BytesIO()
    Image.new('RGB',(5000,5000)).save(data, format='PNG')
    url = f'/api/v1/events/{uuid4()}/gallery/search'
    assert client.post(url, files={'selfie':('x.png',data.getvalue(),'image/png')}).status_code == 413
    assert client.post(url, content=b'x'*(5*1024*1024+65537), headers={'content-type':'multipart/form-data; boundary=x'}).status_code == 413
