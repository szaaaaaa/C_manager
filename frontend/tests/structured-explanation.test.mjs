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
const badge = {};
vm.runInNewContext(transpile(readFileSync(new URL('../src/components/ClassificationBadge.tsx',import.meta.url),'utf8')), {exports:badge,require});
const section={text:'缺少匹配证据，尚未确认',status:'unknown',evidence_ids:[]};
const packet={path:'D:\\model.safetensors',size_human:'5.7 GB',fingerprint:'abc',query:'safetensors model weights format documentation',checked_at:1,evidence:[{id:'W1',kind:'web_excerpt',title:'网页标题',content:'<script>evil()</script>适用版本待核实',url:'https://example.org/docs'}],warnings:['未检查备份']};
test('decision comes first; recovery, uncertainties and citations remain in closed details',()=>{
 const html=renderToStaticMarkup(React.createElement(exports.ExplanationResult,{result:{packet,backend_used:'local',search_status:'ddgs：已读取正文',explanation:{decision:"keep",condition:"",ownership:{...section,text:'用于恢复原来的设置。'},impact:{...section,text:'删除会失去恢复功能。'},recovery:{...section,text:'需要已有备份才能找回。'},advice:{...section,text:'先留着，确认不需要恢复后再处理。'},unknowns:['未确认备份和下载权限']}}}));
 const main=html.slice(0,html.indexOf('<details'));
 assert.ok(main.indexOf('能不能删')<main.indexOf('删了会怎样'));
 assert.ok(main.indexOf('删了会怎样')<main.indexOf('有什么用'));
 assert.ok(main.includes('先留着，确认不需要恢复后再处理。'));
 for(const hidden of ['需要已有备份才能找回','未确认备份和下载权限','ddgs','https://example.org/docs','依据：']) { assert.ok(!main.includes(hidden));assert.ok(html.includes(hidden)); }
 assert.ok(!/<details[^>]*\bopen(?:=|>)/.test(html));
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
 assert.ok(calls[1].args.onSearchEvent);
 await api.explainItem(packet.path,'abc',true,'','','',true,null,'示例软件 功能 用途\nUSMT.PPKG 文件用途 删除影响');
 assert.ok(!('searchProvider' in calls[2].args));assert.ok(!('tavilyKey' in calls[2].args));assert.equal(calls[2].args.searchQuery,'示例软件 功能 用途\nUSMT.PPKG 文件用途 删除影响');
});
test('late generated explanation cannot update a closed panel',async()=>{
 const source=ts.createSourceFile('ExplanationBubble.tsx',readFileSync(new URL('../src/components/ExplanationBubble.tsx',import.meta.url),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 let callback;
 function visit(node){if(ts.isVariableDeclaration(node)&&node.name.getText(source)==='analyze')callback=node.initializer.getText(source);ts.forEachChild(node,visit);}visit(source);assert.ok(callback);
 let resolve;const state={result:null,working:false};
 const context=vm.createContext({item:{path:packet.path},preview:packet,working:false,request:{current:0},settings:{modelSource:'local',tavilyKey:''},question:'',setWorking:x=>{state.working=x;},setFailure(){},setResult:x=>{state.result=x;},setOnline(){},setQuestion(){},setSteps(){},explainItem:()=>new Promise(r=>{resolve=r;})});
 vm.runInContext(transpile(`globalThis.analyze=${callback}`),context);
 const pending=context.analyze(false);context.request.current++;resolve({packet});await pending;assert.equal(state.result,null);
});
test('an unlisted PPKG file has an editable query and an enabled search button',()=>{
 const bubble={};
 const mockedRequire=name=> name==='react' ? {...React,useState:initial=>[initial,()=>{}],useRef:()=>({current:null}),useEffect:()=>{}} : name==='../api' ? {} : name==='./ExplanationResult' ? exports : name==='./ClassificationBadge' ? badge : require(name);
 vm.runInNewContext(transpile(readFileSync(new URL('../src/components/ExplanationBubble.tsx',import.meta.url),'utf8')),{exports:bubble,require:mockedRequire});
 for(const query of ['USMT.PPKG 文件用途 删除影响',null,'示例软件 功能 用途\nUSMT.PPKG 文件用途 删除影响']) {
  const html=renderToStaticMarkup(React.createElement(bubble.ExplanationBubble,{item:{name:'USMT.PPKG',path:'C:\\Recovery\\USMT.PPKG',safety:'yellow'},preview:{...packet,query},loading:false,error:null,onClose(){},settings:{modelSource:'local',searchProvider:'ddgs'}}));
  assert.ok(html.includes(`${query ?? 'USMT.PPKG 文件用途 删除影响'}</textarea>`));
  const button=html.match(/<button([^>]*)>使用上述查询联网分析<\/button>/);
  assert.ok(button);assert.ok(!button[1].includes('disabled'));
  assert.ok(!html.includes('未配置搜索规则'));
 }
});

test('path warnings and managed cleanup advice describe different operations without a second vague verdict',()=>{
 const classification={file_type:'其他',matches:[{rule_id:'5/2/1',category:'系统垃圾',group:'临时文件',label:'系统临时文件',path_pattern:'%CSIDL_WINDOWS%\\Temp',default_selected:true,requires_idle:false}]};
 const label=renderToStaticMarkup(React.createElement(badge.ClassificationBadge,{classification}));
 assert.ok(label.includes('系统临时文件') && label.includes('不代表可以删除'));
 assert.ok(!label.includes('清理候选') && !label.includes('勿直接删'));
 const unknown=renderToStaticMarkup(React.createElement(badge.ClassificationBadge,{classification:{file_type:'其他',matches:[]}}));
 assert.ok(unknown.includes('未命中用途规则'));
 const advice={text:'可以用磁盘清理中的传递优化文件清理，不要手动删。',status:'uncertain',evidence_ids:['W1']};
 const html=renderToStaticMarkup(React.createElement(exports.ExplanationResult,{result:{packet,search_status:'ddgs',explanation:{decision:"keep",condition:"",advice,ownership:section,impact:section,recovery:section,unknowns:['未检查当前任务']}}}));
 const main=html.slice(0,html.indexOf('<details'));
 assert.ok(main.includes(advice.text));
 assert.ok(!main.includes('有条件') && !main.includes('本机适用性'));
 assert.ok(html.includes('本机适用性未完全确认'));
 const withoutUnknowns=renderToStaticMarkup(React.createElement(exports.ExplanationResult,{result:{packet,search_status:'ddgs',explanation:{decision:"keep",condition:"",advice,ownership:section,impact:section,recovery:section,unknowns:[]}}}));
 assert.ok(!withoutUnknowns.includes('还需确认'));

});

test('classification results cannot update a replaced scan and failures are visible', async () => {
 const source=ts.createSourceFile('App.tsx',readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
 let effect;
 function visit(node) {
  if(ts.isCallExpression(node) && node.expression.getText(source)==='useEffect' && node.arguments[0]?.getText(source).includes('classifyFiles(batch)')) effect=node.arguments[0].getText(source);
  ts.forEachChild(node,visit);
 }
 visit(source);assert.ok(effect);
 for(const cancelled of [true,false]) {
  let finish;let updates=0;
  const context=vm.createContext({classificationError:null,results:[{path:'C:\\Windows\\Temp\\a.tmp',is_dir:false}],classifications:{},
   classifyFiles:()=>new Promise(resolve=>{finish=resolve;}),setClassifications(){updates++;},setClassificationError(error){throw new Error(error);}});
  vm.runInContext(transpile(`globalThis.effect=${effect}`),context);
  const cleanup=context.effect();if(cancelled) cleanup();
  finish([{file_type:'其他',matches:[]}]);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(updates,cancelled?0:1);
 }
 let failure;
 const context=vm.createContext({classificationError:null,results:[{path:'D:\\file',is_dir:false}],classifications:{},
  classifyFiles:()=>Promise.reject(new Error('classification unavailable')),setClassifications(){assert.fail('unexpected result');},setClassificationError(error){failure=error;}});
 vm.runInContext(transpile(`globalThis.effect=${effect}`),context);context.effect();await new Promise(resolve=>setImmediate(resolve));
 assert.match(failure,/classification unavailable/);
});

test('all five decisions and necessary conditions are visible before the impact',()=>{
 for(const [decision,label] of Object.entries({direct_delete:'可直接删除',managed_cleanup:'通过系统或软件清理',conditional_delete:'满足条件后可删除',keep:'建议保留',unknown:'暂无法判断'})) {
  const html=renderToStaticMarkup(React.createElement(exports.ExplanationResult,{result:{packet,search_status:'',explanation:{decision,condition:'需要确认的具体事项',ownership:section,impact:section,recovery:section,advice:section,unknowns:[]}}}));
  const main=html.slice(0,html.indexOf('<details'));
  assert.ok(main.includes(label));assert.ok(main.includes('需要确认的具体事项'));
  assert.ok(main.indexOf(label)<main.indexOf('删了会怎样'));
  assert.ok(main.includes(decision==='unknown'?'缺少依据：':'必要条件：'));
 }
});

test('search progress is forwarded and the transcript displays actual queries and failures', async()=>{
 let args;let progress;
 const api={};
 vm.runInNewContext(transpile(readFileSync(new URL('../src/api.ts',import.meta.url),'utf8')),{exports:api,require:()=>({invoke:async(_name,a)=>{args=a;return {};},Channel:class{}})});
 await api.explainItem('D:\\a.bin','hash',true,'','','',true,null,'a.bin 用途',step=>{progress=step;});
 const step={round:2,action:'search',target:'某软件 删除影响',reason:'核实删除影响',missing:['删除后果'],outcome:'失败：网络不可用',goal:'impact',focus:'',site:'',finding:'只找到用途',evidence_ids:[],sources:[]};
 args.onSearchEvent.onmessage(step);assert.equal(progress,step);
 const html=renderToStaticMarkup(React.createElement(exports.SearchTrace,{steps:[step]}));
 for(const text of [step.target,step.reason,step.outcome]) assert.ok(html.includes(text));
});

test('retrieval record separates tool arguments and outcomes from cited evidence summaries',()=>{
 const source={id:'W1',title:'软件帮助 <说明>',url:'https://example.org/help',kind:'web_excerpt'};
 const base={round:1,action:'search',target:'某软件 组件说明 site:example.org',goal:'identity',focus:'',site:'example.org',reason:'查找软件归属依据',finding:'',evidence_ids:[],missing:['组件用途'],outcome:'新增1条来源',sources:[source]};
 const followup={...base,round:2,action:'find_in_page',target:'W1',goal:'purpose',site:'',focus:'vesdk 视频',reason:'核对组件作用',finding:'文档提到视频组件，尚未对应到这个文件。',evidence_ids:['W1'],outcome:'失败：未找到匹配段落',sources:[]};
 const html=renderToStaticMarkup(React.createElement(exports.SearchTrace,{steps:[base,followup]}));
 for(const value of ['检索记录（2步）','核实归属 · 搜索','查明用途 · 页内查找','搜索词：'+base.target,'限定站点：example.org','来源 ID：W1','页内关键词：vesdk 视频','执行结果：'+followup.outcome,'依据摘要（模型整理）：'+followup.finding,'待确认：组件用途']) assert.ok(html.includes(value),value);
 assert.ok(html.includes('aria-label="本步来源"'));
 assert.equal((html.match(/href="https:\/\/example.org\/help"/g)||[]).length,2);
 assert.ok(html.includes('rel="noopener noreferrer"'));
 assert.ok(html.includes('软件帮助 &lt;说明&gt;'));
 assert.ok(!html.includes('来源 ID：W1 vesdk'));
 assert.ok(!html.includes('思维链'));
 const reviewed=renderToStaticMarkup(React.createElement(exports.SearchTrace,{steps:[{...base,action:'review_source',target:'W1',focus:'不匹配：资料属于另一个软件',outcome:'模型判断：归属不匹配',sources:[{...source,kind:'web_document'}]}]}));
 for(const text of ['核对来源归属','来源编号：W1','关联判断（模型判断）：不匹配：资料属于另一个软件','执行结果：模型判断：归属不匹配','已读正文','href="https://example.org/help"']) assert.ok(reviewed.includes(text),text);
 const rejected=renderToStaticMarkup(React.createElement(exports.SearchTrace,{steps:[{...base,action:'reject_sources',target:'W1、W2',focus:'来源介绍另一个软件的组件',outcome:'模型判断：排除2条来源',sources:[]}]}));
 for(const text of ['排除不匹配来源','排除编号：W1、W2','不匹配原因（模型判断）：来源介绍另一个软件的组件','执行结果：模型判断：排除2条来源']) assert.ok(rejected.includes(text),text);
 const unsafe=renderToStaticMarkup(React.createElement(exports.SearchTrace,{steps:[{...base,finding:'<script>bad()</script>',evidence_ids:['W1'],sources:[{...source,url:'javascript:alert(1)'}]}]}));
 assert.ok(!unsafe.includes('href='));
 assert.ok(unsafe.includes('&lt;script&gt;bad()&lt;/script&gt;'));
});
