import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const summary = (status, count = 0) => ({
  status, engine: 'directory', entries_scanned: count, files_matched: count,
  issues: [], excluded_links: [], elapsed_ms: 100,
});
const file = n => ({
  path: String.raw`C:\test\file-${n}.bin`, name: `file-${n}.bin`,
  size: n + 1, size_human: '1 KB', is_dir: false, children_count: 0, safety: 'yellow',
});

test('channel verification catches lost, repeated and out-of-order batches, and ignores late messages', async () => {
  for (const sequences of [[0, 1], [1], [0, 0], [1, 0]]) {
    let channel;
    const delivered = [];
    const exports = {};
    vm.runInNewContext(transpile(apiSource), {
      exports,
      require: () => ({
        Channel: class {},
        invoke: async (_name, args) => {
          channel = args.onEvent;
          for (const sequence of sequences) {
            channel.onmessage({ type: 'files', sequence, files: [file(sequence)] });
          }
          return { scan_id: 1, summary: summary('completed', 2), batches_sent: 2, transport_error: null };
        },
      }),
    });
    const completion = await exports.scanDrive('C:\\', 0, msg => delivered.push(msg));
    assert.equal(completion.stream_verified, sequences.join() === '0,1');
    const accepted = delivered.length;
    channel.onmessage({ type: 'files', sequence: 2, files: [file(2)] });
    assert.equal(delivered.length, accepted);
    assert.equal(new Set(delivered.map(msg => msg.sequence)).size, accepted);
  }
});

const appSource = ts.createSourceFile('App.tsx', readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8'),
  ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const callbacks = {};
function visit(node) {
  if (ts.isVariableDeclaration(node) && ['flushFileBatch', 'handleStartScan'].includes(node.name.getText(appSource))) {
    callbacks[node.name.getText(appSource)] = node.initializer.arguments[0].getText(appSource);
  }
  ts.forEachChild(node, visit);
}
visit(appSource);
assert.equal(Object.keys(callbacks).length, 2);

function setup(scanDrive, getScanResults = () => { throw new Error('unexpected reload'); }) {
  const state = { results: [], progress: null, backendError: null, scanning: false, scanRun: 0 };
  const context = vm.createContext({
    scanDrive, getScanResults, scanRunningRef: { current: false }, explainRequestRef: { current: 0 },
    fileBatchRef: { current: [] }, flushTimerRef: { current: null },
    setTimeout: () => 1, clearTimeout: () => {},
    setExplainLoading() {}, setSelectedItem() {}, setExplanation() {}, setExplainError() {}, setView() {},
    setScanRun: value => { state.scanRun = value(state.scanRun); },
    setScanning: value => { state.scanning = value; },
    setBackendError: value => { state.backendError = value; },
    setResults: value => { state.results = typeof value === 'function' ? value(state.results) : value; },
    setProgress: value => { state.progress = typeof value === 'function' ? value(state.progress) : value; },
  });
  for (const [name, callback] of Object.entries(callbacks)) {
    vm.runInContext(transpile(`globalThis.${name} = ${callback}`), context);
  }
  return { state, context };
}

test('the final short batch is retained, sorted once at completion, and a cancelled scan stays cancelled', async () => {
  const { state, context } = setup(async (_root, _min, receive) => {
    receive({ type: 'files', sequence: 0, files: [file(0), file(2), file(1)] });
    return { scan_id: 1, summary: summary('cancelled', 3), stream_verified: true, transport_error: null };
  });
  await context.handleStartScan({ root: 'C:\\', min_size_mb: 0 });
  assert.deepEqual(Array.from(state.results, f => f.size), [3, 2, 1]);
  assert.equal(state.progress.status, 'cancelled');
  assert.equal(state.scanning, false);
  assert.equal(context.scanRunningRef.current, false);
});

test('a failed scan preserves partial results and never becomes an empty successful scan', async () => {
  const { state, context } = setup(async (_root, _min, receive) => {
    receive({ type: 'files', sequence: 0, files: [file(1)] });
    throw new Error('failed to enumerate');
  });
  await context.handleStartScan({ root: 'C:\\', min_size_mb: 0 });
  assert.equal(state.results.length, 1);
  assert.equal(state.progress.status, 'failed');
  assert.match(state.progress.error, /failed to enumerate/);
});

test('missing batches are replaced with every retained page, including results beyond 1000', async () => {
  const all = Array.from({ length: 1103 }, (_, n) => file(n));
  const offsets = [];
  const { state, context } = setup(async (_root, _min, receive) => {
    receive({ type: 'files', sequence: 0, files: [file(2), file(2)] });
    return { scan_id: 9, summary: summary('completed', all.length), stream_verified: false, transport_error: null };
  }, async (scanId, offset) => {
    assert.equal(scanId, 9);
    offsets.push(offset);
    return all.slice(offset, offset + 1000);
  });
  await context.handleStartScan({ root: 'C:\\', min_size_mb: 0 });
  assert.deepEqual(offsets, [0, 1000]);
  assert.equal(state.results.length, 1103);
  assert.equal(new Set(state.results.map(f => f.path)).size, 1103);
  assert.equal(state.results[0].size, 1103);
  assert.equal(state.progress.status, 'completed');
});

test('concurrent starts are rejected until the active scan has finished', async () => {
  let finish;
  let starts = 0;
  const { state, context } = setup(() => {
    starts++;
    return new Promise(resolve => { finish = resolve; });
  });
  const first = context.handleStartScan({ root: 'C:\\', min_size_mb: 0 });
  await context.handleStartScan({ root: 'D:\\', min_size_mb: 0 });
  assert.equal(starts, 1);
  finish({ summary: summary('completed'), stream_verified: true, transport_error: null });
  await first;
  assert.equal(state.scanning, false);
});

const resultExports = {};
vm.runInNewContext(transpile(readFileSync(new URL('../src/components/ScanResults.tsx', import.meta.url), 'utf8')), {
  exports: resultExports,
  require: name => {
    if (name === 'framer-motion') return { motion: new Proxy({}, { get: (_target, tag) => tag }) };
    if (name === 'lucide-react') return new Proxy({}, { get: () => () => null });
    if (name === './SafetyBadge') return { SafetyBadge: () => null };
    if (name === '../api') return {};
    return require(name);
  },
});

test('result rendering caps rows at 100 while reporting the complete collection', () => {
  const items = Array.from({ length: 1103 }, (_, n) => file(n));
  const html = renderToStaticMarkup(React.createElement(resultExports.ScanResults, {
    items, progress: { ...summary('completed', items.length), error: null },
    selectedPath: null, onItemClick() {},
  }));
  assert.equal((html.match(/title="在资源管理器中打开"/g) ?? []).length, 100);
  assert.match(html, /1103/);
  assert.match(html, /下一页/);
});

test('empty partial, cancelled and failed results retain their distinct status and diagnostic paths', () => {
  for (const status of ['partial', 'cancelled', 'failed']) {
    const html = renderToStaticMarkup(React.createElement(resultExports.ScanResults, {
      items: [], progress: {
        ...summary(status), error: null,
        issues: [{ path: 'C:\\denied', stage: 'read_dir', error: 'Access denied' }],
      },
      selectedPath: null, onItemClick() {},
    }));
    assert.match(html, /结果不完整|未覆盖范围/);
    assert.match(html, /C:\\denied/);
    assert.doesNotMatch(html, /所选范围内没有匹配此筛选条件的文件/);
  }
});
