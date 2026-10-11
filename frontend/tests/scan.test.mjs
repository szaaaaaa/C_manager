import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import { createHash, webcrypto } from 'node:crypto';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
const summary = (status, count = 0) => ({
  status, engine: 'mft_dual', entries_scanned: count, files_matched: count,
  issues: [], excluded_links: [], elapsed_ms: 100,
});
const file = n => ({
  path: String.raw`C:\test\file-${n}.bin`, name: `file-${n}.bin`,
  size: n + 1, size_human: '1 KB', is_dir: false, children_count: 0, safety: 'yellow',
});
const checksum = (position, files) => createHash('sha256')
  .update(JSON.stringify([position, files.map(f => [f.path, String(f.size)])])).digest('hex');
function loadApi(invoke, crypto = webcrypto) {
  const exports = {};
  vm.runInNewContext(transpile(apiSource), {
    exports, crypto, TextEncoder,
    require: () => ({ Channel: class {}, invoke }),
  });
  return exports;
}

test('all engine choices reach the backend without changing the selected engine', async () => {
  for (const engine of ['mft_dual']) {
    const api = loadApi(async (_name, args) => {
      assert.equal(args.engine, engine);
      assert.equal(args.root, 'D:\\');
      assert.equal(args.minSizeMb, 100);
      return { summary: { ...summary('failed'), engine }, batches_sent: 0, transport_error: null };
    });
    const completion = await api.scanDrive('D:\\', 100, () => {}, engine);
    assert.equal(completion.summary.engine, engine);
    assert.equal(completion.summary.status, 'failed');
  }
});

test('verification progress does not count as file batches and reaches application state', async () => {
  const verification = { checked: 256, total: 520, path_errors: 1, hard_link_queries: 2, workers: 4 };
  let currentState;
  const api = loadApi(async (_name, args) => {
    args.onEvent.onmessage({ type: 'verification', verification });
    assert.deepEqual(currentState.progress.verification, verification);
    return { summary: { ...summary('partial'), verification }, batches_sent: 0, transport_error: null };
  });
  const { state, context } = setup(api.scanDrive);
  currentState = state;
  await context.handleStartScan({ root: 'C:\\', min_size_mb: 500, engine: 'mft_dual' });
  assert.deepEqual(state.progress.verification, verification);
  assert.equal(state.progress.status, 'partial');
});

test('channel verification catches lost, repeated and out-of-order batches, and ignores late messages', async () => {
  for (const sequences of [[0, 1], [1], [0, 0], [1, 0]]) {
    let channel;
    const delivered = [];
    const exports = loadApi(async (_name, args) => {
      channel = args.onEvent;
      for (const sequence of sequences) {
        const files = [file(sequence)];
        channel.onmessage({ type: 'files', sequence, files, checksum: checksum(sequence, files) });
      }
      return { scan_id: 1, summary: summary('completed', 2), batches_sent: 2, transport_error: null };
    });
    const completion = await exports.scanDrive('C:\\', 0, msg => delivered.push(msg));
    assert.equal(completion.stream_verified, sequences.join() === '0,1');
    const accepted = delivered.length;
    channel.onmessage({ type: 'files', sequence: 2, files: [file(2)] });
    assert.equal(delivered.length, accepted);
    assert.equal(new Set(delivered.map(msg => msg.sequence)).size, accepted);
  }
});

test('equal-count replacement, size corruption and unsafe integers cannot pass content verification', async () => {
  const original = [file(0), file(1)];
  for (const received of [[file(0), file(0)], [file(0), { ...file(1), size: 99 }],
    [file(0), { ...file(1), size: 2 ** 53 }]]) {
    const delivered = [];
    const api = loadApi(async (_name, args) => {
      args.onEvent.onmessage({ type: 'files', sequence: 0, files: received, checksum: checksum(0, original) });
      return { summary: summary('completed', 2), batches_sent: 1, transport_error: null };
    });
    assert.equal((await api.scanDrive('C:\\', 0, msg => delivered.push(msg))).stream_verified, false);
    assert.equal(delivered.length, 0);
  }
});

test('pages verify content and offset, including Unicode, escaping, large files and empty pages', async () => {
  const files = [{ ...file(0), path: 'C:\\中文😀\\quote"\t\n.bin', size: 20 * 1024 ** 3 }];
  assert.equal(checksum(1000, files), '0fc9c6f6f5e338e619400d00451e69543d708aee316d3a805dc8b0b1609a1cc2');
  for (const page of [files, []]) {
    const api = loadApi(async () => ({ files: page, checksum: checksum(1000, page) }));
    assert.deepEqual(await api.getScanResults(1, 1000), page);
    await assert.rejects(api.getScanResults(1, 0), /核对失败/);
  }
  const corrupt = loadApi(async () => ({ files: [file(9)], checksum: checksum(0, files) }));
  await assert.rejects(corrupt.getScanResults(1, 0), /核对失败/);
});

test('completion and failure both drain pending checks, without delivering files after settlement', async () => {
  for (const fails of [false, true]) {
    let release;
    let settled = false;
    const delivered = [];
    const files = [file(0)];
    const api = loadApi(async (_name, args) => {
      args.onEvent.onmessage({ type: 'files', sequence: 0, files, checksum: checksum(0, files) });
      if (fails) throw new Error('invoke failed');
      return { summary: summary('cancelled', 1), batches_sent: 1, transport_error: null };
    }, { subtle: { digest: (...args) => new Promise(resolve => {
      release = async () => resolve(await webcrypto.subtle.digest(...args));
    }) } });
    const result = api.scanDrive('C:\\', 0, msg => delivered.push(msg)).then(
      value => { settled = true; return value; },
      error => { settled = true; return error; });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(settled, false);
    await release();
    const completion = await result;
    assert.equal(delivered.length, 1);
    if (fails) assert.match(completion.message, /invoke failed/);
    else assert.equal(completion.stream_verified, true);
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
    setExplainLoading() {}, setSelectedItem() {}, setPreview() {}, setExplainError() {}, setView() {},
    setActiveScanConfig() {}, setClassifications() {}, setClassificationError() {},
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

test('starting from the UI forwards the chosen engine and keeps its failure status', async () => {
  for (const engine of ['mft_dual']) {
    const { state, context } = setup(async (_root, _min, _receive, selectedEngine) => {
      assert.equal(selectedEngine, engine);
      return { summary: { ...summary('failed'), engine }, stream_verified: true, transport_error: null };
    });
    await context.handleStartScan({ root: 'D:\\', min_size_mb: 100, engine });
    assert.equal(state.progress.engine, engine);
    assert.equal(state.progress.status, 'failed');
  }
});

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

test('content corruption triggers verified recovery; corrupt recovery pages leave the scan failed', async () => {
  const files = [file(0), file(1)];
  for (const corruptPage of [false, true]) {
    let reloads = 0;
    const api = loadApi(async (name, args) => {
      if (name === 'scan_drive') {
        args.onEvent.onmessage({ type: 'files', sequence: 0,
          files: [file(0), file(0)], checksum: checksum(0, files) });
        return { scan_id: 1, summary: summary('completed', 2), batches_sent: 1, transport_error: null };
      }
      assert.equal(name, 'get_scan_results');
      reloads++;
      return { files: corruptPage ? [file(0), file(9)] : files, checksum: checksum(0, files) };
    });
    const { state, context } = setup(api.scanDrive, api.getScanResults);
    await context.handleStartScan({ root: 'C:\\', min_size_mb: 0 });
    assert.equal(reloads, 1);
    assert.equal(state.progress.status, corruptPage ? 'failed' : 'completed');
    assert.equal(state.results.length, corruptPage ? 0 : 2);
    if (corruptPage) assert.match(state.backendError, /核对失败/);
  }
});

test('100k-record synthetic channel verification benchmark', {
  skip: process.env.SCAN_TRANSPORT_BENCH !== '1',
}, async () => {
  const all = Array.from({ length: 100_000 }, (_, n) => file(n));
  const messages = [];
  for (let offset = 0; offset < all.length; offset += 256) {
    const files = all.slice(offset, offset + 256);
    const sequence = messages.length;
    messages.push({ type: 'files', sequence, files, checksum: checksum(sequence, files) });
  }
  for (let round = 0; round < 3; round++) {
    let received = 0;
    const api = loadApi(async (_name, args) => {
      for (const message of messages) args.onEvent.onmessage(message);
      return { summary: summary('completed', all.length), batches_sent: messages.length, transport_error: null };
    });
    const start = performance.now();
    const completion = await api.scanDrive('C:\\', 0, message => { received += message.files.length; });
    const elapsed_ms = performance.now() - start;
    assert.equal(completion.stream_verified, true);
    assert.equal(received, all.length);
    console.log(JSON.stringify({ benchmark: 'synthetic-node-channel-verification', round,
      files: received, batches: messages.length, elapsed_ms }));
  }
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
    if (name === './ClassificationBadge') return { ClassificationBadge: () => null };
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

test('results identify the actual engine and scan settings, with full-report copying available', () => {
  const html = renderToStaticMarkup(React.createElement(resultExports.ScanResults, {
    config: { root: 'D:\\', min_size_mb: 100, engine: 'mft_dual' },
    items: [file(0)], progress: { ...summary('partial', 1), engine: 'mft_dual', error: null,
      verification: { total: 520, checked: 519, path_errors: 1, hard_link_queries: 5, workers: 4 },
      mft_records: { base_records: 530, extension_records: 50, logical_entries: 530 },
      issues: [{ path: 'file-reference:123', stage: 'path_resolution', error: 'missing parent' }] },
    selectedPath: null, onItemClick() {},
  }));
  assert.match(html, /MFT 双读取 worker/);
  assert.match(html, /D:\\/);
  assert.match(html, /100/);
  assert.match(html, /复制扫描报告/);
  assert.match(html, /已核验 519 \/ 520/);
  assert.match(html, /硬链接补查 5 次/);
  assert.match(html, /path_resolution: 1/);
  assert.match(html, /扩展记录 50（不是独立文件）/);
});

test('experimental routes show unverified size filtering explicitly', () => {
  for (const engine of ['mft_dual']) {
    const html = renderToStaticMarkup(React.createElement(resultExports.ScanResults, {
      items: [], progress: { ...summary('partial'), engine, size_filtered: 1700000, error: null },
      selectedPath: null, onItemClick() {},
    }));
    assert.match(html, /扫描结果/);
    assert.match(html, /1,700,000/);
    assert.match(html, /未逐文件核验，变化尚未补查/);
  }
});

test('copying a scan report includes every path and exact size, and surfaces clipboard failures', async () => {
  const source = ts.createSourceFile('ScanResults.tsx', readFileSync(new URL('../src/components/ScanResults.tsx', import.meta.url), 'utf8'),
    ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let callback;
  function find(node) {
    if (ts.isVariableDeclaration(node) && node.name.getText(source) === 'handleCopyReport') callback = node.initializer.getText(source);
    ts.forEachChild(node, find);
  }
  find(source);
  assert.ok(callback);
  const items = Array.from({ length: 1103 }, (_, n) => file(n));
  for (const fails of [false, true]) {
    let copied;
    let message;
    const context = vm.createContext({ items, progress: summary('completed', items.length),
      config: { root: 'C:\\', engine: 'mft_dual', min_size_mb: 0 },
      setReportMessage: value => { message = value; },
      navigator: { clipboard: { writeText: async text => {
        if (fails) throw new Error('denied'); copied = JSON.parse(text);
      } } },
    });
    vm.runInContext(transpile(`globalThis.copyReport = ${callback}`), context);
    await context.copyReport();
    if (fails) assert.match(message, /复制失败.*denied/);
    else {
      assert.equal(copied.config.engine, 'mft_dual');
      assert.equal(copied.files.length, 1103);
      assert.deepEqual(copied.files, items.map(({ path, size }) => ({ path, size })));
      assert.match(message, /已复制/);
    }
  }
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
    assert.match(html, status === 'partial' ? /扫描结果/ : /结果不完整/);
    assert.match(html, /C:\\denied/);
    assert.doesNotMatch(html, /所选范围内没有匹配此筛选条件的文件/);
  }
});
