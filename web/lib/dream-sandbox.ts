export type DreamWidget = {
  id: string; kind: 'number' | 'metric' | 'checklist' | 'board' | 'text';
  title: string; description: string; value: number; minimum: number; maximum: number;
  unit: string; items: string[]; terms: { input_id: string; coefficient: number }[];
  constant: number; divide_by: number;
};
export type DreamArtifact = {
  title: string; premise: string; widgets: DreamWidget[];
  inspiration: { source: number; quote: string }[];
  how_to_test: string[]; limitations: string;
};

// Only this trusted renderer executes. Model output is text/data, never HTML or JS.
export function dreamDocument(artifact: DreamArtifact, nonce: string): string {
  const data = JSON.stringify(artifact).replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026');
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; media-src 'none'; frame-src 'none'; worker-src 'none'; form-action 'none'; base-uri 'none'">
<meta name="referrer" content="no-referrer"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dream Lab sandbox</title><style>
:root{color-scheme:dark}body{margin:0;padding:24px;background:#101321;color:#edf0ff;font:16px system-ui;line-height:1.5}h1{font-size:28px}h2{font-size:18px;margin-top:0}p{color:#bbc2db}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}section{padding:20px;background:#1b2035;border:1px solid #3b4360;border-radius:16px}input{font:inherit;padding:10px;border:1px solid #737f9d;border-radius:8px;background:#101321;color:#fff;max-width:90%}output{display:block;font-size:30px;color:#c4b5fd}label{display:block;margin:10px 0}input[type=checkbox]{margin-right:10px}li{padding:6px}#checks{padding:12px;border:1px solid #7c6ea6;border-radius:8px}small{color:#bbc2db}
</style></head><body><h1 id="title"></h1><p id="premise"></p><p id="checks" role="status">Checking prototype controls…</p><main id="widgets"></main><p><small>Disposable offline sandbox · illustrative inputs stay inside this preview · close to reset.</small></p>
<script nonce="${nonce}">
'use strict';
const artifact=${data};
const values={},outputs=[],checks=[];
function node(tag,text,parent){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(parent)parent.appendChild(el);return el;}
document.getElementById('title').textContent=artifact.title;
document.getElementById('premise').textContent=artifact.premise;
for(const w of artifact.widgets){
 const box=node('section',undefined,document.getElementById('widgets'));
 node('h2',w.title,box);if(w.description)node('p',w.description,box);
 if(w.kind==='number'){
  values[w.id]=w.value;const label=node('label',w.unit||'Value',box);const input=node('input',undefined,label);
  input.type='number';input.min=String(w.minimum);input.max=String(w.maximum);input.step='any';input.value=String(w.value);input.setAttribute('aria-label',w.title);
  input.addEventListener('input',()=>{const n=Number(input.value);values[w.id]=Number.isFinite(n)?Math.min(w.maximum,Math.max(w.minimum,n)):w.value;recalculate();});
  checks.push(()=>{input.value=String(w.maximum);input.dispatchEvent(new Event('input'));if(values[w.id]!==w.maximum)throw Error('Input failed');input.value=String(w.value);input.dispatchEvent(new Event('input'));});
 }else if(w.kind==='metric'){
  const out=node('output','',box);outputs.push({w,out});
 }else if(w.kind==='checklist'){
  const boxes=w.items.map(text=>{const label=node('label',undefined,box);const c=node('input',undefined,label);c.type='checkbox';label.appendChild(document.createTextNode(text));return c;});
  const progress=node('p','',box);const update=()=>{progress.textContent=boxes.filter(c=>c.checked).length+' / '+boxes.length+' complete';};
  boxes.forEach(c=>c.addEventListener('change',update));update();
  checks.push(()=>{boxes[0].checked=true;boxes[0].dispatchEvent(new Event('change'));if(!progress.textContent.startsWith('1 /'))throw Error('Checklist failed');boxes[0].checked=false;update();});
 }else if(w.kind==='board'){
  const filter=node('input',undefined,box);filter.type='search';filter.placeholder='Filter cards';filter.setAttribute('aria-label','Filter '+w.title);
  const list=node('ul',undefined,box);const cards=w.items.map(text=>node('li',text,list));
  const update=()=>cards.forEach(c=>{c.hidden=!c.textContent.toLowerCase().includes(filter.value.toLowerCase());});filter.addEventListener('input',update);
  checks.push(()=>{filter.value='__dream_no_match_94b__';filter.dispatchEvent(new Event('input'));if(cards.some(c=>!c.hidden))throw Error('Filter failed');filter.value='';update();});
 }
}
function recalculate(){for(const {w,out} of outputs){const n=(w.constant+w.terms.reduce((sum,t)=>sum+values[t.input_id]*t.coefficient,0))/w.divide_by;out.textContent=Number.isFinite(n)&&Math.abs(n)<=1e15?n.toLocaleString(undefined,{maximumFractionDigits:4})+' '+w.unit:'Outside calculation budget';}}
recalculate();
try{checks.forEach(check=>check());recalculate();document.getElementById('checks').textContent='Browser interaction checks: '+checks.length+' passed. Try the prototype below.';}
catch{document.getElementById('checks').textContent='A browser interaction check failed. Treat this prototype as needing review.';}
</script></body></html>`;
}
