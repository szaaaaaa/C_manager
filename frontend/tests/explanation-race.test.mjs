import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

// Exercise the actual callbacks without adding a DOM runner or exporting UI internals.
const source = ts.createSourceFile('App.tsx', readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8'),
  ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const callbacks = {};
function visit(node) {
  if (ts.isVariableDeclaration(node) && ['handleItemClick', 'handleCloseExplanation'].includes(node.name.getText(source))) {
    callbacks[node.name.getText(source)] = node.initializer.arguments[0].getText(source);
  }
  ts.forEachChild(node, visit);
}
visit(source);
assert.equal(Object.keys(callbacks).length, 2);

function setup() {
  const state = { selected: null, explanation: null, error: null, loading: false };
  const pending = [];
  const context = vm.createContext({
    selectedItem: null, savedSettings: { modelSource: 'local' }, explainRequestRef: { current: 0 },
    setSelectedItem: item => { state.selected = item; context.selectedItem = item; },
    setExplanation: value => { state.explanation = value; },
    setExplainError: value => { state.error = value; },
    setExplainLoading: value => { state.loading = value; },
    explainItem: path => new Promise((resolve, reject) => pending.push({ path, resolve, reject })),
  });
  for (const [name, callback] of Object.entries(callbacks)) {
    vm.runInContext(ts.transpileModule(`globalThis.${name} = ${callback}`, {}).outputText, context);
  }
  return { state, pending, context };
}
const file = path => ({ path, size: 100, is_dir: false });

test('a late answer cannot replace the currently selected file', async () => {
  const { context, state, pending } = setup();
  const first = context.handleItemClick(file('A'));
  const second = context.handleItemClick(file('B'));
  pending[1].resolve({ path: 'B', explanation: 'B answer' });
  await second;
  pending[0].resolve({ path: 'A', explanation: 'A answer' });
  await first;
  assert.equal(state.selected.path, 'B');
  assert.equal(state.explanation.path, 'B');
});

test('a stale error cannot clear the newer request loading state', async () => {
  const { context, state, pending } = setup();
  const first = context.handleItemClick(file('A'));
  const second = context.handleItemClick(file('B'));
  pending[0].reject('A failed');
  await first;
  assert.equal(state.error, null);
  assert.equal(state.loading, true);
  pending[1].resolve({ path: 'B' });
  await second;
  assert.equal(state.loading, false);
});

test('closing the explanation invalidates pending output', async () => {
  const { context, state, pending } = setup();
  const request = context.handleItemClick(file('A'));
  context.handleCloseExplanation();
  pending[0].resolve({ path: 'A' });
  await request;
  assert.equal(state.selected, null);
  assert.equal(state.explanation, null);
  assert.equal(state.loading, false);
});
