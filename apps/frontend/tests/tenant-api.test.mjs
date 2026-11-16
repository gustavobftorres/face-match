import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';

const source = await readFile(new URL('../src/lib/tenant-api.ts', import.meta.url), 'utf8');
const { code } = await transform(source, { loader: 'ts', format: 'esm' });
const api = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

test('session and event calls stay same-origin and preserve status', async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ nonce: 'nonce' }) };
  };
  assert.deepEqual(await api.createChallenge(), { nonce: 'nonce' });
  await api.loginWithGoogle('credential');
  await api.getEvent('id/other');
  assert.equal(calls[0][0], '/api/v1/session/challenge');
  assert.equal(calls[0][1].credentials, 'same-origin');
  assert.deepEqual(JSON.parse(calls[1][1].body), { id_token: 'credential' });
  assert.equal(calls[2][0], '/api/v1/events/id%2Fother');
  globalThis.fetch = async () => ({ ok: false, status: 404 });
  await assert.rejects(api.getTenant(), error => error instanceof api.ApiError && error.status === 404);
});

test('logout sends the CSRF cookie in the required header', async () => {
  globalThis.document = { cookie: 'other=x; __Host-fm_csrf=abc%2D123' };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/v1/session');
    assert.equal(options.method, 'DELETE');
    assert.equal(options.headers['X-CSRF-Token'], 'abc-123');
    return { ok: true, status: 204 };
  };
  await api.logout();
  document.cookie = '';
  assert.throws(() => api.logout(), /CSRF/);
});

test('gallery uses CSRF, multipart, same-origin URLs, and no Drive token', async () => {
  globalThis.document = { cookie: '__Host-fm_csrf=csrf-value' };
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return { ok: true, status: 200, json: async () => ({ id: 'search', photos: [] }) };
  };
  const selfie = new File(['photo'], 'selfie.jpg', { type: 'image/jpeg' });
  await api.searchGallery('event', selfie);
  await api.startGalleryIndex('event', 'folder');
  await api.latestGalleryJob('event');
  assert.equal(calls[0][0], '/api/v1/events/event/gallery/search');
  assert.equal(calls[0][1].body.get('selfie').name, 'selfie.jpg');
  assert.equal(calls[0][1].headers['X-CSRF-Token'], 'csrf-value');
  assert.equal(calls[0][1].headers['Content-Type'], undefined);
  assert.deepEqual(JSON.parse(calls[1][1].body), { folder: 'folder' });
  assert.equal(calls[2][0], '/api/v1/events/event/gallery/jobs/latest');
  assert.equal(api.galleryPhotoUrl('event', 'search', 'photo'), '/api/v1/events/event/gallery/searches/search/photos/photo');
});

test('organizer admin calls are same-origin, CSRF-protected and never send a tenant id', async () => {
  globalThis.document = { cookie: '__Host-fm_csrf=csrf-value' };
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return { ok: true, status: 200, json: async () => ({}) };
  };
  await api.getAdminAccess();
  await api.listAdminEvents();
  await api.getAdminBranding();
  await api.createAdminEvent({ name: 'Corrida', slug: 'corrida', description: null });
  await api.updateAdminEvent('id/x', { name: 'Novo' });
  await api.setAdminEventStatus('id/x', 'publish');
  await api.setAdminEventStatus('id/x', 'unpublish');
  await api.setAdminEventStatus('id/x', 'close');
  await api.updateAdminBranding('ocean');
  await api.uploadAdminLogo(new File(['png'], 'logo.png', { type: 'image/png' }));
  await api.deleteAdminLogo();
  const [read, create, update, publish, unpublish, close, palette, logo, remove] = [calls[0], calls[3], calls[4], calls[5], calls[6], calls[7], calls[8], calls[9], calls[10]];
  assert.deepEqual(calls.slice(0, 3).map(c => c[0]), ['/api/v1/admin/access', '/api/v1/admin/events', '/api/v1/admin/branding']);
  assert.equal(read[1].credentials, 'same-origin');
  assert.equal(read[1].headers, undefined);
  assert.equal(create[0], '/api/v1/admin/events');
  assert.equal(create[1].method, 'POST');
  assert.deepEqual(JSON.parse(create[1].body), { name: 'Corrida', slug: 'corrida', description: null });
  assert.equal(update[0], '/api/v1/admin/events/id%2Fx');
  assert.equal(update[1].method, 'PATCH');
  assert.deepEqual([publish[0], unpublish[0], close[0]], ['/api/v1/admin/events/id%2Fx/publish', '/api/v1/admin/events/id%2Fx/unpublish', '/api/v1/admin/events/id%2Fx/close']);
  assert.equal(palette[1].method, 'PUT');
  assert.deepEqual(JSON.parse(palette[1].body), { palette: 'ocean' });
  assert.equal(logo[0], '/api/v1/admin/branding/logo');
  assert.equal(logo[1].body.get('logo').name, 'logo.png');
  assert.equal(logo[1].headers['Content-Type'], undefined);
  assert.equal(remove[1].method, 'DELETE');
  for (const [, options] of [create, update, publish, unpublish, close, palette, logo, remove]) {
    assert.equal(options.headers['X-CSRF-Token'], 'csrf-value');
    assert.ok(!String(options.body ?? '').includes('tenant'));
  }
});

test('admin mutations refuse to run without the CSRF cookie and surface 403 status', () => {
  globalThis.document = { cookie: '' };
  assert.throws(() => api.createAdminEvent({ name: 'x', slug: 'xxx' }), /CSRF/);
  assert.throws(() => api.setAdminEventStatus('e', 'publish'), /CSRF/);
  assert.throws(() => api.uploadAdminLogo(new File(['x'], 'l.png')), /CSRF/);
});

test('admin access denial keeps the HTTP status for the not-authorized state', async () => {
  globalThis.fetch = async () => ({ ok: false, status: 403 });
  await assert.rejects(api.getAdminAccess(), error => error instanceof api.ApiError && error.status === 403);
});
