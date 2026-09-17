// Canvas/DOM unit harness: executes the shipped offline viewer without a browser.
// Run: node tests/viewer-smoke.cjs examples/proposals
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const folder=process.argv[2];if(!folder)throw Error('Pass a generated proposal folder');
const html=fs.readFileSync(path.join(folder,'viewer.html'),'utf8');
let paintCalls=0;
const context2d=new Proxy({}, {get(t,k){return (...args)=>{for(const v of args)if(typeof v==='number')assert(Number.isFinite(v),`${k} received a nonfinite coordinate`);paintCalls++}},set(t,k,v){t[k]=v;return true}});
class Element{
 constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.checked=false;this.clientWidth=800;this.clientHeight=tag==='canvas'?440:175;this.dataset={}}
 append(...nodes){this.children.push(...nodes);if(this.tag==='select'&&!this.value&&nodes[0])this.value=nodes[0].value}
 replaceChildren(){this.children=[];this.value=''}
 setAttribute(k,v){this[k]=v}get lastChild(){return this.children.at(-1)}get options(){return this.children}
 getContext(){return context2d}remove(){}setPointerCapture(){}
}
const elements=new Map([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new Element(m[1])]));
const views=['perspective','front','side','top'].map(v=>{let el=new Element('button');el.dataset.view=v;return el});
let scope;
const document={getElementById:id=>{assert(elements.has(id),id);return elements.get(id)},createElement:tag=>new Element(tag),querySelector:()=>new Element(),querySelectorAll:()=>views,head:{append(el){const source=el.src.split('?')[0];vm.runInContext(fs.readFileSync(path.join(folder,source),'utf8'),scope);el.onload()}}};
scope=vm.createContext({document,window:{devicePixelRatio:1},ResizeObserver:class{observe(){}},setInterval(){},console});
vm.runInContext(html.split('<script>')[1].split('</script>')[0],scope);
const initial=JSON.parse(fs.readFileSync(path.join(folder,'viewer-state.json'),'utf8'));
if(initial.candidates.length===0 && initial.baseline.result){
 assert.equal(elements.get('selection').textContent,'Baseline');
 assert.equal(elements.get('polars').hidden,false);
 assert.equal(elements.get('frequency').children.length,initial.baseline.result.response.frequencies_hz.length);
 assert.equal(elements.get('objective').textContent,initial.baseline.result.score.objective===null?'Not ranked':Number(initial.baseline.result.score.objective).toLocaleString(undefined,{maximumFractionDigits:2}));
 elements.get('frequency').value=String(Math.min(1,initial.baseline.result.response.frequencies_hz.length-1));elements.get('frequency').onchange();
 assert(paintCalls>1000);
 console.log('Real analysis viewer passed: geometry, frequency selection, finite polar drawing, unrankable result status.');
 process.exit(0);
}
assert.equal(elements.get('selection').textContent,'Baseline');
assert.equal(elements.get('objective').textContent,'Not simulated');
assert.equal(elements.get('acoustic-empty').hidden,false);
assert.equal(elements.get('polars').hidden,true);
assert(paintCalls>1000,'3D drawing should execute');
elements.get('candidates').children[1].onclick();
assert.equal(elements.get('selection').textContent,'Candidate 1');
assert.equal(elements.get('parameters').children.length,11);
assert.equal(elements.get('slot').textContent,'HF only');
assert.equal(elements.get('lf-legend').hidden,true);
elements.get('overlay').checked=true;elements.get('overlay').onchange();
elements.get('wire').checked=true;elements.get('wire').onchange();
for(const button of views)button.onclick();
elements.get('geometry').onkeydown({key:'ArrowLeft',preventDefault(){}});
elements.get('geometry').onwheel({deltaY:50,preventDefault(){}});
elements.get('reset').onclick();
elements.get('refresh-button').onclick();
assert.equal(elements.get('selection').textContent,'Candidate 1','refresh must preserve selection');
// In-memory fixture only, not saved in the example or represented as BEM output.
const data=JSON.parse(fs.readFileSync(path.join(folder,'viewer-state.json'),'utf8'));
data.candidates[0].result={score:{objective:.2},response:{frequencies_hz:[1000],angles_deg:[-90,0,90],horizontal_db:[[-24,0,-24]],vertical_db:[[-40,0,-40]]}};
scope.window.concordUpdate(data);
assert.equal(elements.get('polars').hidden,false);
assert.equal(elements.get('acoustic-empty').hidden,true);
assert.equal(elements.get('objective').textContent,'0.2');
assert.equal(elements.get('frequency').children.length,1);
console.log('Viewer smoke passed: drawing, selection, overlay, views, zoom, refresh, result charts.');

data.candidates[0].result.score={objective:null,reason:'No -6 dB crossings'};
scope.window.concordUpdate(data);
assert.equal(elements.get('objective').textContent,'Not ranked');
assert.equal(elements.get('polars').hidden,false);
assert(elements.get('analysis-note').textContent.includes('No -6 dB crossings'));
