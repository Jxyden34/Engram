import assert from 'node:assert/strict';
import { constants, generateKeyPairSync, privateEncrypt, sign } from 'node:crypto';
import { createRequire } from 'node:module';
import test from 'node:test';

// Resolve the packages used by Expo/React Native, not additional test-only copies.
const require = createRequire(import.meta.url);
const expo = createRequire(require.resolve('expo/package.json'));
const cli = createRequire(expo.resolve('@expo/cli/package.json'));
const native = createRequire(require.resolve('react-native/package.json'));
const postcss = createRequire(cli.resolve('postcss'));
const micromatch = createRequire(cli.resolve('micromatch'));
const xcodeRequire = createRequire(cli.resolve('xcode'));
const shellQuote = native('shell-quote');
const { SourceMapConsumer, SourceNode } = postcss('source-map-js');
const braces = micromatch('braces');
const forge = cli('node-forge');
const uuid = xcodeRequire('uuid');

test('shell quoting rejects line terminators after comments', () => {
  for (const newline of ['\n', '\r', '\u2028', '\u2029']) {
    assert.throws(() => shellQuote.quote(['echo', 'ok', { comment: 'note' }, 'a' + newline + 'id;#']), TypeError);
  }
});

test('shell quoting preserves ordinary argument boundaries and URL fragments', () => {
  const args = ['echo', 'a b', "don't", 'https://example.test/#fragment', 'x;y'];
  assert.deepEqual(shellQuote.parse(shellQuote.quote(args)), args);
  assert.equal(shellQuote.quote(['echo', { comment: 'note' }, 'text']), 'echo #note text');
});

const flatMap = { version: 3, sources: ['a.js'], sourcesContent: ['a'], names: [], mappings: 'AAAA' };
const indexedMap = (line, map = flatMap, column = 0) => ({
  version: 3, sections: [{ offset: { line, column }, map }],
});

test('indexed source maps reject huge and invalid offsets, including nested sums', () => {
  for (const line of [1e9, -1, 0.5, '1', Infinity, NaN]) {
    assert.throws(() => new SourceMapConsumer(indexedMap(line)), /Section offset/);
  }
  assert.throws(() => new SourceMapConsumer(indexedMap(6e6, indexedMap(6e6))), /Section offset/);
  assert.throws(() => new SourceMapConsumer(indexedMap(0, flatMap, -1)), /Section offset/);
});

test('source maps preserve generated code and ordinary nested sections', () => {
  const consumer = new SourceMapConsumer(indexedMap(2, indexedMap(3)));
  const lines = [];
  consumer.eachMapping(mapping => lines.push(mapping.generatedLine));
  assert.deepEqual(lines, [6]);
  assert.equal(SourceNode.fromStringWithSourceMap('var x;\n', consumer).toString(), 'var x;\n');
});

test('PostCSS still generates valid CSS source maps', async () => {
  const css = 'a { color: red; }';
  const result = await cli('postcss')([]).process(css, { from: 'input.css', to: 'output.css', map: { inline: false } });
  assert.ok(result.css.startsWith(css));
  assert.deepEqual(result.map.toJSON().sources, ['input.css']);
});

test('UUID namespace generators reject partial writes before modifying buffers', () => {
  for (const generate of [uuid.v3, uuid.v5]) {
    for (const [length, offset] of [[8, 4], [16, -1], [16, 1]]) {
      const buffer = new Uint8Array(length).fill(0xaa);
      assert.throws(() => generate('x', uuid.v5.DNS, buffer, offset), RangeError);
      assert.deepEqual(buffer, new Uint8Array(length).fill(0xaa));
    }
    const buffer = new Uint8Array(20).fill(0xaa);
    assert.equal(generate('x', uuid.v5.DNS, buffer, 4), buffer);
    assert.ok(uuid.validate(uuid.stringify(buffer, 4)));
  }
});

test('Xcode still generates distinct uppercase 24-character project IDs', () => {
  const project = cli('xcode').project('unused.pbxproj');
  project.hash = { project: { objects: {} } };
  const first = project.generateUuid();
  const second = project.generateUuid();
  assert.match(first, /^[A-F0-9]{24}$/);
  assert.match(second, /^[A-F0-9]{24}$/);
  assert.notEqual(first, second);
});

test('brace walkers reject excessive nesting for strings and direct ASTs', () => {
  const deep = '{'.repeat(4998) + 'a,b' + '}'.repeat(4998);
  const parens = '('.repeat(1000) + 'x' + ')'.repeat(1000);
  const ast = braces.parse(deep);
  for (const method of ['compile', 'expand', 'stringify']) {
    for (const input of [deep, parens, ast]) {
      assert.throws(() => braces[method](input), { name: 'SyntaxError', message: 'Input nesting exceeds maximum depth (256)' });
    }
  }
  // Invalid/dollar nodes enter stringify from expand rather than its usual walker.
  assert.throws(() => braces.expand('$' + '{'.repeat(1000) + 'x' + '}'.repeat(1000)), SyntaxError);
});

test('brace matching, ranges, escapes and ordinary nesting keep working', () => {
  assert.deepEqual(braces.expand('src/{a,b}/{1..3}.js'), ['src/a/1.js', 'src/a/2.js', 'src/a/3.js', 'src/b/1.js', 'src/b/2.js', 'src/b/3.js']);
  assert.equal(braces.compile('src/{a,b}.js'), 'src/(a|b).js');
  const nested = '{'.repeat(50) + 'a,b' + '}'.repeat(50);
  assert.equal(braces.stringify(braces.parse(nested)), nested);
  assert.doesNotThrow(() => braces.compile(nested));
  assert.deepEqual(braces.expand('hello\\{world\\}'), ['hello{world}']);
  assert.deepEqual(cli('micromatch')(['src/a.js', 'src/b.ts', 'src/c.txt'], 'src/*.{js,ts}'), ['src/a.js', 'src/b.ts']);
});

test('brace depth boundary covers internal stringify and cyclic ASTs', () => {
  const allowed = '{'.repeat(255) + 'a,b' + '}'.repeat(255);
  const rejected = '{' + allowed + '}';
  for (const method of ['compile', 'expand', 'stringify']) {
    assert.doesNotThrow(() => braces[method](allowed));
    assert.throws(() => braces[method](rejected), SyntaxError);
    const cyclic = { type: 'root', nodes: [] };
    cyclic.nodes.push(cyclic);
    assert.throws(() => braces[method](cyclic), SyntaxError);
  }
  assert.throws(() => braces.parse('{1..' + '{'.repeat(300) + 'a,b' + '}'.repeat(300) + ',2}'), SyntaxError);
});

const keys = generateKeyPairSync('rsa', { modulusLength: 1024, publicExponent: 3 });
const publicKey = forge.pki.publicKeyFromPem(keys.publicKey.export({ type: 'spki', format: 'pem' }).toString());
const digest = forge.md.sha256.create().update('Engram dependency regression').digest().getBytes();
const asn1 = forge.asn1;
const node = (type, constructed, value) => asn1.create(asn1.Class.UNIVERSAL, type, constructed, value);

function signatureForDigestInfo({ parameters = true, extraAlgorithm = [], extraOuter = [] } = {}) {
  const algorithm = [node(asn1.Type.OID, false, asn1.oidToDer(forge.oids.sha256).getBytes())];
  if (parameters) algorithm.push(node(asn1.Type.NULL, false, ''));
  algorithm.push(...extraAlgorithm);
  const info = node(asn1.Type.SEQUENCE, true, [node(asn1.Type.SEQUENCE, true, algorithm), node(asn1.Type.OCTETSTRING, false, digest), ...extraOuter]);
  const der = Buffer.from(asn1.toDer(info).getBytes(), 'binary');
  const padding = Buffer.alloc(128 - der.length - 3, 0xff);
  const encoded = Buffer.concat([Buffer.from([0, 1]), padding, Buffer.from([0]), der]);
  return privateEncrypt({ key: keys.privateKey, padding: constants.RSA_NO_PADDING }, encoded).toString('binary');
}

test('RSA verification rejects extra nested and outer DigestInfo elements', () => {
  const garbage = node(asn1.Type.OCTETSTRING, false, 'unconsumed');
  for (const options of [
    { extraAlgorithm: [garbage] },
    { parameters: false, extraAlgorithm: [garbage] },
    { extraAlgorithm: [node(asn1.Type.NULL, false, '')] },
    { extraOuter: [garbage] },
  ]) {
    assert.throws(() => publicKey.verify(digest, signatureForDigestInfo(options)), /valid RSASSA-PKCS1-v1_5 DigestInfo/);
  }
});

test('RSA verification accepts valid SHA-256 with optional NULL and rejects wrong messages', () => {
  for (const parameters of [true, false]) {
    assert.equal(publicKey.verify(digest, signatureForDigestInfo({ parameters })), true);
  }
  const signature = sign('sha256', Buffer.from('Engram dependency regression'), keys.privateKey).toString('binary');
  assert.equal(publicKey.verify(digest, signature), true);
  const otherDigest = forge.md.sha256.create().update('other message').digest().getBytes();
  assert.equal(publicKey.verify(otherDigest, signature), false);
});

test('all Expo signing and Xcode importer contexts use the same repaired packages', () => {
  const updates = createRequire(require.resolve('expo-updates/package.json'));
  for (const importer of [cli, updates]) {
    const certificates = createRequire(importer.resolve('@expo/code-signing-certificates'));
    assert.equal(certificates('node-forge'), forge);
  }
  for (const importer of [expo, cli]) {
    const plugins = createRequire(importer.resolve('@expo/config-plugins/package.json'));
    const project = createRequire(plugins.resolve('xcode'));
    assert.equal(project('uuid'), uuid);
  }
});

test('Expo code-signing certificates, CSRs and manifest signatures still verify', () => {
  const certificates = cli('@expo/code-signing-certificates');
  const keyPair = certificates.convertKeyPairPEMToKeyPair({
    publicKeyPEM: keys.publicKey.export({ type: 'spki', format: 'pem' }).toString(),
    privateKeyPEM: keys.privateKey.export({ type: 'pkcs1', format: 'pem' }).toString(),
  });
  const certificate = certificates.generateSelfSignedCodeSigningCertificate({
    keyPair, commonName: 'Engram test only',
    validityNotBefore: new Date(Date.now() - 60000),
    validityNotAfter: new Date(Date.now() + 60000),
  });
  const decoded = certificates.convertCertificatePEMToCertificate(certificates.convertCertificateToCertificatePEM(certificate));
  assert.doesNotThrow(() => certificates.validateSelfSignedCertificate(decoded, keyPair));
  const signature = certificates.signBufferRSASHA256AndVerify(keyPair.privateKey, decoded, Buffer.from('Engram dependency regression'));
  assert.equal(decoded.publicKey.verify(digest, Buffer.from(signature, 'base64').toString('binary')), true);
  const csr = certificates.generateCSR(keyPair, 'Engram test only');
  assert.equal(certificates.convertCSRPEMToCSR(certificates.convertCSRToCSRPEM(csr)).verify(), true);
});
