import assert from 'node:assert/strict';
import test from 'node:test';
import { clearOfflineLibrary, readOfflineLibrary, saveOfflineLibrary, searchOffline, toggleFavorite } from './offline.ts';

function store() {
  const values = new Map();
  return {
    values,
    async getItemAsync(key) { return values.get(key) ?? null; },
    async setItemAsync(key, value) { values.set(key, value); },
    async deleteItemAsync(key) { values.delete(key); },
  };
}

const session = { origin: 'https://beta.example.com', username: 'jayden', projectId: 'personal' };
const memory = (id, content) => ({ id, title: `Memory ${id}`, content, memory_type: 'general', updated_at: '2026-09-29T00:00:00Z' });

test('offline memories remain scoped to account, server and project', async () => {
  const device = store();
  await saveOfflineLibrary(device, session, [memory('one', 'Personal private content')]);
  assert.equal((await readOfflineLibrary(device, session)).items[0].content, 'Personal private content');
  for (const changed of [{ username: 'other' }, { projectId: 'work' }, { origin: 'https://other.example.com' }]) {
    assert.deepEqual((await readOfflineLibrary(device, { ...session, ...changed })).items, []);
  }
  const indexKey = [...device.values.keys()].find(key => key.endsWith('_index'));
  device.values.set(indexKey, '{broken');
  assert.deepEqual((await readOfflineLibrary(device, session)).items, []);
});

test('large memories become marked excerpts and old entries are pruned', async () => {
  const device = store();
  await saveOfflineLibrary(device, session, [memory('old', 'old'), memory('long', '🔥'.repeat(3000))]);
  const first = await readOfflineLibrary(device, session);
  assert.equal(first.items[1].truncated, true);
  assert.ok(first.items[1].content.endsWith('…'));
  assert.ok(encodeURIComponent(JSON.stringify(first.items[1])).length <= 1800);
  await saveOfflineLibrary(device, session, [memory('new', 'new')]);
  assert.deepEqual((await readOfflineLibrary(device, session)).items.map(item => item.id), ['new']);
  assert.equal([...device.values.keys()].some(key => key.endsWith('_old')), false);
  await clearOfflineLibrary(device, session);
  assert.deepEqual((await readOfflineLibrary(device, session)).items, []);
});

test('offline search matches all terms in the saved excerpt', () => {
  const items = [memory('one', 'The blue tablet'), memory('two', 'The red phone')];
  assert.deepEqual(searchOffline(items, 'BLUE tablet').map(item => item.id), ['one']);
  assert.deepEqual(searchOffline(items, 'blue phone'), []);
});

test('favourites survive recent-list rotation, refresh content and retain excerpt labels', async () => {
  const device = store();
  await saveOfflineLibrary(device, session, [memory('keep', 'Original content')]);
  const timestamp = (await readOfflineLibrary(device, session)).savedAt;
  await toggleFavorite(device, session, memory('keep', 'Original content'));
  assert.equal((await readOfflineLibrary(device, session)).savedAt, timestamp);
  const recent = Array.from({ length: 30 }, (_, i) => memory(`recent-${i}`, 'recent'));
  let saved = await saveOfflineLibrary(device, session, recent);
  assert.equal(saved.items.length, 20);
  assert.equal(saved.items[0].id, 'keep');
  assert.equal(saved.items[0].favorite, true);
  assert.deepEqual((await readOfflineLibrary(device, { ...session, projectId: 'work' })).items, []);
  saved = await saveOfflineLibrary(device, session, [memory('keep', 'Updated content'), ...recent]);
  assert.equal(saved.items[0].content, 'Updated content');
  saved = await toggleFavorite(device, session, saved.items[0]);
  assert.equal(saved.items.some(item => item.favorite), false);
  saved = await toggleFavorite(device, session, memory('long-favourite', '🔥'.repeat(3000)));
  assert.equal(saved.items[0].truncated, true);
  saved = await toggleFavorite(device, session, saved.items[0]);
  assert.equal(saved.items.find(item => item.id === 'long-favourite').truncated, true);
  for (const [key, value] of device.values) if (!key.endsWith('_index')) assert.ok(encodeURIComponent(value).length <= 1800);
});

test('favourites enforce the per-project limit without losing saved copies', async () => {
  const device = store();
  for (let i = 0; i < 10; i++) await toggleFavorite(device, session, memory(`saved-${i}`, 'important'));
  const before = await readOfflineLibrary(device, session);
  await assert.rejects(() => toggleFavorite(device, session, memory('extra', 'extra')), /10 favourites/);
  assert.deepEqual(await readOfflineLibrary(device, session), before);
  await toggleFavorite(device, session, before.items[0]);
  await toggleFavorite(device, session, memory('extra', 'extra'));
  assert.equal((await readOfflineLibrary(device, session)).items.filter(item => item.favorite).length, 10);
  await clearOfflineLibrary(device, session);
  assert.deepEqual((await readOfflineLibrary(device, session)).items, []);
});
