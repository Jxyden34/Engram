import assert from 'node:assert/strict';
import test from 'node:test';
import { appendTranscript } from './voice.ts';

test('reviewed speech appends without replacing typed capture or truncating either', () => {
  assert.equal(appendTranscript('Typed context', ' Spoken note '), 'Typed context\nSpoken note');
  assert.equal(appendTranscript('', ' Spoken note '), 'Spoken note');
  assert.throws(() => appendTranscript('Keep me', ''), /No speech/);
  assert.throws(() => appendTranscript('x'.repeat(1200), 'Extra'), /too long/);
});
