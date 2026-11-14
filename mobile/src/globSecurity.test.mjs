import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const require = createRequire(import.meta.url);
const expo = createRequire(require.resolve('expo/package.json'));
const cli = createRequire(expo.resolve('@expo/cli/package.json'));
const updates = createRequire(require.resolve('expo-updates/package.json'));
const fingerprint = createRequire(updates.resolve('@expo/fingerprint/package.json'));
const globVariants = [];
const minimatchVariants = [];
for (const importer of [cli, fingerprint]) {
  const globRoot = dirname(importer.resolve('glob/package.json'));
  const matcher = createRequire(importer.resolve('glob'));
  const minimatchRoot = dirname(matcher.resolve('minimatch/package.json'));
  globVariants.push(importer('glob'), importer('glob/raw'),
    await import(pathToFileURL(join(globRoot, importer('glob/package.json').exports['.'].import.default)).href),
    await import(pathToFileURL(join(globRoot, 'dist/esm/index.js')).href));
  minimatchVariants.push(matcher('minimatch'),
    await import(pathToFileURL(join(minimatchRoot, 'dist/esm/index.js')).href));
}

const fingerprintMatcherRoot = dirname(fingerprint.resolve('minimatch/package.json'));
minimatchVariants.push(fingerprint('minimatch'),
  await import(pathToFileURL(join(fingerprintMatcherRoot, 'dist/esm/index.js')).href));

test('Expo glob entry points use the cancellation repair in both importers', () => {
  for (const offset of [0, 4]) {
    assert.equal(globVariants[offset].Glob, globVariants[offset + 1].Glob);
    assert.equal(globVariants[offset + 2].Glob, globVariants[offset + 3].Glob);
  }
});

function fixture(t) {
  const cwd = fs.mkdtempSync(join(tmpdir(), 'engram-glob-'));
  t.after(() => {
    assert.equal(dirname(resolve(cwd)), resolve(tmpdir()));
    fs.rmSync(cwd, { recursive: true, force: true });
  });
  for (const name of ['src/a.ts', 'src/b.txt', '.hidden/note.ts', 'node_modules/ignored.ts', 'packages/a/index.ts']) {
    fs.mkdirSync(dirname(join(cwd, name)), { recursive: true });
    fs.writeFileSync(join(cwd, name), name);
  }
  for (let i = 0; i < 24; i++) {
    fs.mkdirSync(join(cwd, 'tree', String(i), 'child'), { recursive: true });
    fs.writeFileSync(join(cwd, 'tree', String(i), 'child', 'file.txt'), 'fixture');
  }
  return cwd;
}

test('glob cancellation stops new directory reads across published entry points', async t => {
  const cwd = fixture(t);
  for (const glob of globVariants) {
    for (const scenario of [
      { pattern: '**', extra: {} },
      { pattern: '*', extra: { stat: true } },
      { pattern: ['src/*', 'packages/*'], extra: {} },
      { pattern: '**', extra: { realpath: true, stat: true, follow: true, nodir: true } },
    ]) {
      for (const mode of ['promise', 'stream', 'iterator', 'sync', 'syncStream']) {
        const controller = new AbortController();
        const reason = new Error('cancel fixture walk');
        let reads = 0;
        let metadataAfterAbort = 0;
        const count = () => { if (++reads === 1) controller.abort(reason); };
        const metadata = () => { if (controller.signal.aborted) metadataAfterAbort++; };
        const countedFs = {
          ...fs,
          readdir(...args) { count(); return fs.readdir(...args); },
          readdirSync(...args) { count(); return fs.readdirSync(...args); },
          lstatSync(...args) { metadata(); return fs.lstatSync(...args); },
          realpathSync(...args) { metadata(); return fs.realpathSync(...args); },
          readlinkSync(...args) { metadata(); return fs.readlinkSync(...args); },
          promises: {
            ...fs.promises,
            lstat(...args) { metadata(); return fs.promises.lstat(...args); },
            realpath(...args) { metadata(); return fs.promises.realpath(...args); },
            readlink(...args) { metadata(); return fs.promises.readlink(...args); },
          },
        };
        const options = { cwd, fs: countedFs, signal: controller.signal, ...scenario.extra };
        if (mode === 'sync') {
          assert.throws(() => glob.globSync(scenario.pattern, options), error => error === reason);
        } else if (mode === 'syncStream') {
          // A synchronous stream may finish before an async iterator subscribes.
          // Its cancellation must still stop filesystem work.
          const walk = glob.globStreamSync(scenario.pattern, options);
          walk.on('error', error => assert.equal(error, reason));
          try { for await (const ignored of walk) { /* drain */ } }
          catch (error) { assert.equal(error, reason); }
        } else {
          await assert.rejects(async () => {
            if (mode === 'promise') await glob.glob(scenario.pattern, options);
            else {
              const walk = mode === 'stream' ? glob.globStream(scenario.pattern, options) : glob.globIterate(scenario.pattern, options);
              for await (const ignored of walk) { /* drain until cancellation */ }
            }
          }, error => error === reason, mode);
        }
        // Allow the already-issued read to complete; it must not start another.
        await new Promise(resolve => setTimeout(resolve, 50));
        assert.equal(reads, 1, mode);
        assert.equal(metadataAfterAbort, 0, mode + ' metadata');
      }
    }
    const signal = AbortSignal.abort(new Error('already canceled'));
    await assert.rejects(glob.glob('**', { cwd, signal }), /already canceled/);
    assert.throws(() => glob.globSync('**', { cwd, signal }), /already canceled/);
  }
});

test('glob keeps workspace, dotfile, ignore and paused stream matching', async t => {
  const cwd = fixture(t);
  const options = { cwd, nodir: true, dot: true, posix: true, ignore: 'node_modules/**' };
  const expected = ['.hidden/note.ts', 'packages/a/index.ts', 'src/a.ts'];
  for (const glob of globVariants) {
    assert.deepEqual((await glob.glob('**/*.ts', options)).sort(), expected);
    assert.deepEqual(glob.globSync('**/*.ts', options).sort(), expected);
    const stream = glob.globStream('**/*', options);
    await new Promise(resolve => setTimeout(resolve, 20));
    const values = [];
    for await (const value of stream) values.push(value);
    assert.deepEqual(values.sort(), glob.globSync('**/*', options).sort());
  }
  const { everyMatchAsync, anyMatchAsync } = cli('./build/src/utils/glob.js');
  assert.deepEqual((await everyMatchAsync('packages/*/index.ts', { cwd, posix: true })).sort(), ['packages/a/index.ts']);
  assert.equal((await anyMatchAsync('**/*.ts', { cwd })).length, 1);
});

test('minimatch bounds optimization growth while preserving ordinary matching', () => {
  for (const { Minimatch } of minimatchVariants) {
    // Eight splits are small even on the vulnerable implementation.
    const pattern = Array(8).fill('**/../a/b').join('/');
    assert.throws(() => new Minimatch(pattern, { optimizationLevel: 2, braceExpandMax: 32 }),
      { name: 'RangeError', message: 'Pattern optimization exceeds braceExpandMax (32)' });
    assert.equal(new Minimatch(pattern, { optimizationLevel: 2, braceExpandMax: 256 })
      .match(Array(8).fill('x/a/b').join('/')), true);
    const small = new Minimatch('**/../a/b/**/../c/d', { optimizationLevel: 2 });
    assert.equal(small.set.length, 4);
    assert.equal(small.match('../a/b/../c/d'), true);
    assert.equal(small.match('x/a/b/y/c/d'), true);
    const large = new Minimatch('{x,*}/{0..500}', { optimizationLevel: 2 });
    assert.equal(new Minimatch('{x,*}/{0..499}', { optimizationLevel: 2 }).set.length, 500);
    assert.equal(large.set.length, 1002);
    assert.equal(large.match('y/500'), true);
    assert.equal(large.match('.y/5'), false);
    assert.equal(new Minimatch('src/!(*.test).ts').match('src/main.ts'), true);
    assert.equal(new Minimatch('src/!(*.test).ts').match('src/main.test.ts'), false);
    assert.equal(new Minimatch('**/*.ts', { dot: true }).match('.hidden/main.ts'), true);
  }
  const paths = fingerprint('./build/utils/Path.js');
  assert.equal(paths.isIgnoredPath('node_modules/pkg/index.js', ['**/node_modules/**']), true);
  assert.equal(paths.isIgnoredPath('src/main.ts', ['**/node_modules/**']), false);
  const pattern = Array(8).fill('**/../a/b').join('/');
  const file = Array(8).fill('x/a/b').join('/');
  assert.equal(paths.isIgnoredPath(file, [pattern], { optimizationLevel: 2 }), true);
  assert.throws(() => paths.isIgnoredPath(file, [pattern], { optimizationLevel: 2, braceExpandMax: 32 }), RangeError);
});
