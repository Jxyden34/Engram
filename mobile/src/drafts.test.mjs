import assert from 'node:assert/strict';
import test from 'node:test';
import { draftsFor, newDraft, readDrafts, removeDraft, saveDraft, updateDraft } from './drafts.ts';

function store() {
  const values = new Map();
  return {
    values,
    async getItemAsync(key) { return values.get(key) ?? null; },
    async setItemAsync(key, value) { values.set(key, value); },
    async deleteItemAsync(key) { values.delete(key); },
  };
}

const account = { origin: 'https://beta.example.com', username: 'jayden', projectId: 'personal' };

test('captures stay with their account and project until removed', async () => {
  const device = store();
  const personal = newDraft(account, '', 'A thought\nwith context');
  const work = newDraft({ ...account, projectId: 'work' }, 'Work note', 'Private work content');
  await saveDraft(device, personal);
  await saveDraft(device, work);
  const saved = await readDrafts(device);
  assert.equal(personal.title, 'A thought');
  assert.deepEqual(draftsFor(saved, account).map(item => item.id), [personal.id]);
  assert.equal(draftsFor(saved, { ...account, username: 'someone-else' }).length, 0);
  await updateDraft(device, { ...personal, content: 'Revised thought' });
  assert.equal(draftsFor(await readDrafts(device), account)[0].content, 'Revised thought');
  await removeDraft(device, personal.id);
  assert.deepEqual((await readDrafts(device)).map(item => item.id), [work.id]);
});

test('oversized captures are rejected before secure storage is changed', async () => {
  const device = store();
  await assert.rejects(saveDraft(device, newDraft(account, '', 'x'.repeat(2000))), /too long/);
  assert.equal(device.values.size, 0);
});

test('a failed index update rolls back the saved payload', async () => {
  const device = store();
  const setItemAsync = device.setItemAsync;
  device.setItemAsync = async (key, value) => {
    if (key === 'engram_capture_index_v1') throw new Error('storage full');
    await setItemAsync(key, value);
  };
  await assert.rejects(saveDraft(device, newDraft(account, '', 'Keep me safe')), /storage full/);
  assert.equal(device.values.size, 0);
});
