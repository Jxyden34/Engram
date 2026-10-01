import assert from 'node:assert/strict';
import test from 'node:test';
import { relatedMemory, versionCapture } from './memoryTools.ts';

test('connection navigation selects the other endpoint in either direction', () => {
  const link = { from_memory_id: 'first', to_memory_id: 'second', from_title: 'First memory', to_title: 'Second memory' };
  assert.deepEqual(relatedMemory(link, 'first'), { id: 'second', title: 'Second memory' });
  assert.deepEqual(relatedMemory(link, 'second'), { id: 'first', title: 'First memory' });
  assert.equal(relatedMemory(link, 'unrelated'), null);
  assert.equal(relatedMemory({ ...link, to_memory_id: 'first' }, 'first'), null);
});

test('version reuse requires readable text and never discards content', () => {
  const version = { snapshot: { title: 'Title'.repeat(40), content: 'Original text'.repeat(1000) } };
  const seed = versionCapture(version);
  assert.equal(seed.title.length, 100);
  assert.equal(seed.content, version.snapshot.content);
  assert.throws(() => versionCapture({ snapshot: {} }), /no readable/);
  assert.throws(() => versionCapture({ snapshot: { title: 'Title', content: '  ' } }), /no readable/);
});
