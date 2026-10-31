import test from 'node:test';
import assert from 'node:assert/strict';
import { internalReturnPath } from './return-path.ts';

const origin = 'https://engram.example.com';

test('rejects external, malformed and normalization-based return destinations', () => {
  for (const value of [null, '', 'memories', 'https://attacker.example', 'javascript:alert(1)',
    '//attacker.example', '///attacker.example', '/\\attacker.example', '/safe\\..\\attacker.example',
    '/\t/attacker.example', '/\r/attacker.example', '/\n/attacker.example', '/\u0000evil', '/\u007fevil',
    '/safe/..//attacker.example', '/safe/%2e%2e//attacker.example']) {
    assert.equal(internalReturnPath(value, origin), '/', JSON.stringify(value));
  }
  assert.equal(internalReturnPath('/memories', 'invalid origin'), '/');
});

test('preserves internal paths, OAuth authorization queries and fragments', () => {
  for (const value of ['/', '/memories', '/memories/record-id?view=history#version-2',
    '/oauth/authorize?client_id=https%3A%2F%2Fclient.example%2Fmetadata&redirect_uri=https%3A%2F%2Fclient.example%2Fcallback&state=a%2Fb%2Bc&scope=mcp%3Ause+memory%3Aread#consent']) {
    assert.equal(internalReturnPath(value, origin), value);
  }
  assert.equal(internalReturnPath('/memories/../settings?tab=keys#new', origin), '/settings?tab=keys#new');
  assert.equal(internalReturnPath('/oauth/authorize?redirect_uri=https%3A%2F%2Fclient.example', 'http://localhost:8080'), '/oauth/authorize?redirect_uri=https%3A%2F%2Fclient.example');
});
