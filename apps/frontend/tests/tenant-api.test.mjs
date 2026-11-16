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
