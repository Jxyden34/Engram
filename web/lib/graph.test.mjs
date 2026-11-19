import test from 'node:test';
import assert from 'node:assert/strict';
import {filterGraph,layoutGraph,graphBounds,matchesEntity,nodeRadius} from './graph.ts';
const node=(id,type='concept',count=1)=>({id,name:id,entity_type:type,memory_count:count});
const edge=(id,a,b,confidence=.95)=>({id,from_entity_id:a,to_entity_id:b,relation_type:'relates to',confidence});
const graph={nodes:[node('alpha','project'),{...node('beta','server'),aliases:['homelab']},node('gamma','server'),node('isolated')],edges:[edge('a','alpha','beta'),edge('b','beta','gamma',.6),edge('broken','alpha','missing')]};

test('search retains direct neighbours but does not expand transitively or leak missing endpoints',()=>{
 const result=filterGraph(graph,'ALPHA','',0);
 assert.deepEqual(result.nodes.map(n=>n.id),['alpha','beta']);
 assert.deepEqual(result.edges.map(e=>e.id),['a']);
 assert(matchesEntity(graph.nodes[1],'HOMElaB'));
 assert.deepEqual(filterGraph(graph,'homelab','',.7).nodes.map(n=>n.id),['alpha','beta']);
 assert.equal(filterGraph(graph,'unmatched','',0).nodes.length,0);
});

test('type, confidence and focus apply to both ends of every returned relationship',()=>{
 const typed=filterGraph(graph,'','server',.7);
 assert.deepEqual(typed.nodes.map(n=>n.id),['beta','gamma']);
 assert.equal(typed.edges.length,0);
 assert.deepEqual(filterGraph(graph,'','',.7,'beta').nodes.map(n=>n.id),['alpha','beta']);
 assert.deepEqual(filterGraph(graph,'','',0,'isolated').nodes.map(n=>n.id),['isolated']);
 for(const result of [typed,filterGraph(graph,'','',0)]){
  const ids=new Set(result.nodes.map(n=>n.id));
  assert(result.edges.every(e=>ids.has(e.from_entity_id)&&ids.has(e.to_entity_id)));
 }
});

test('layout is stable across response ordering, finite, and fits labels including disconnected nodes',()=>{
 const positions=layoutGraph(graph);
 assert.deepEqual(positions,layoutGraph({nodes:[...graph.nodes].reverse(),edges:[...graph.edges].reverse()}));
 const bounds=graphBounds(graph.nodes,positions);
 for(const p of positions.values()){
  assert(Number.isFinite(p.x)&&Number.isFinite(p.y));
  assert(p.x>=bounds.x+99&&p.x<=bounds.x+bounds.width-99);
  assert(p.y>=bounds.y+64&&p.y<=bounds.y+bounds.height-64);
 }
 assert.deepEqual(layoutGraph({nodes:[],edges:[]}),new Map());
 assert(graphBounds([],new Map()).width>0);
 assert.equal(layoutGraph({nodes:[node('alone')],edges:[edge('self','alone','alone')]}).size,1);
 assert.equal(nodeRadius(node('negative','other',-2)),13);
});

test('the maximum API sample stays separated and linked pairs are pulled together',()=>{
 const nodes=Array.from({length:120},(_,i)=>node(String(i).padStart(3,'0'),'server',i%12));
 const edges=Array.from({length:60},(_,i)=>edge(String(i),nodes[i*2].id,nodes[i*2+1].id));
 const positions=layoutGraph({nodes,edges});
 let closest=Infinity;
 for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
  const a=positions.get(nodes[i].id),b=positions.get(nodes[j].id);
  closest=Math.min(closest,Math.hypot(a.x-b.x,a.y-b.y));
 }
 assert(closest>28,`closest nodes ${closest}`);
 const mean=edges.reduce((sum,e)=>{const a=positions.get(e.from_entity_id),b=positions.get(e.to_entity_id);return sum+Math.hypot(a.x-b.x,a.y-b.y)},0)/edges.length;
 assert(mean<150,`mean linked distance ${mean}`);
});
