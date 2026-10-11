import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const require = createRequire(import.meta.url);
const transpile = source => ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const exports = {};
vm.runInNewContext(transpile(readFileSync(new URL('../src/components/ExplanationResult.tsx',import.meta.url),'utf8')), {exports,require});
const section={text:'缺少匹配证据，尚未确认',status:'unknown',evidence_ids:[]};
const packet={path:'D:\\model.safetensors',size_human:'5.7 GB',fingerprint:'abc',query:'safetensors model weights format documentation',checked_at:1,evidence:[{id:'W1',kind:'web_excerpt',title:'网页标题',content:'<script>evil()</script>适用版本待核实',url:'https://example.org/docs'}],warnings:['未检查备份']};
test('four sections, unknowns, source text and search failure remain visible; HTML is escaped',()=>{
 const html=renderToStaticMarkup(React.createElement(exports.ExplanationResult,{result:{packet,backend_used:'local',search_status:'联网搜索失败：超时',explanation:{ownership:section,impact:section,recovery:section,advice:section,unknowns:['未确认备份和下载权限']}}}));
 for(const text of ['它是谁的','删了影响什么','能不能找回来','怎么处理更合适','未确认备份和下载权限','联网搜索失败','https://example.org/docs']) assert.ok(html.includes(text));
 assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));
 assert.ok(html.includes('noopener noreferrer'));
});
test('preview does not invoke a model or search; generation forwards explicit opt-in and snapshot',async()=>{
 const calls=[];const api={};
 vm.runInNewContext(transpile(readFileSync(new URL('../src/api.ts',import.meta.url),'utf8')),{exports:api,require:()=>({invoke:async(name,args)=>{calls.push({name,args});return packet;},Channel:class{}})});
 await api.prepareExplanation(packet.path);
 assert.equal(calls.length,1);assert.equal(calls[0].name,'prepare_explanation');assert.deepEqual(Object.keys(calls[0].args),['path']);
 await api.explainItem(packet.path,'abc',false,'','','',true);
 assert.equal(calls[1].args.allowSearch,false);assert.equal(calls[1].args.fingerprint,'abc');assert.equal(calls[1].args.question,null);
});
test('late generated explanation cannot update a closed panel',async()=>{
 const source=ts.createSourceFile('ExplanationBubble.tsx',readFileSync(new URL('../src/components/ExplanationBubble.tsx',import.meta.url),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 let callback;
 function visit(node){if(ts.isVariableDeclaration(node)&&node.name.getText(source)==='analyze')callback=node.initializer.getText(source);ts.forEachChild(node,visit);}visit(source);assert.ok(callback);
 let resolve;const state={result:null,working:false};
 const context=vm.createContext({item:{path:packet.path},preview:packet,working:false,request:{current:0},settings:{modelSource:'local',tavilyKey:''},question:'',setWorking:x=>{state.working=x;},setFailure(){},setResult:x=>{state.result=x;},setOnline(){},setQuestion(){},explainItem:()=>new Promise(r=>{resolve=r;})});
 vm.runInContext(transpile(`globalThis.analyze=${callback}`),context);
 const pending=context.analyze(false);context.request.current++;resolve({packet});await pending;assert.equal(state.result,null);
});
