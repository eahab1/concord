// DOM/canvas execution test; no claim of browser visual inspection.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const folder=process.argv[2],html=fs.readFileSync(path.join(folder,'viewer.html'),'utf8');
let paints=0;const ctx=new Proxy({}, {get:()=> (...args)=>{args.forEach(v=>{if(typeof v==='number')assert(Number.isFinite(v))});paints++},set:()=>true});
class E{constructor(tag){this.tag=tag;this.children=[];this.value='';this.clientWidth=800;this.clientHeight=300}append(...c){this.children.push(...c);if(this.tag==='select'&&!this.value)this.value=c[0].value}replaceChildren(){this.children=[];this.value=''}get options(){return this.children}getContext(){return ctx}getAttribute(k){return this[k]}remove(){}}
const els=new Map([...html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g)].map(m=>[m[2],new E(m[1])]));let scope;
const document={getElementById:id=>{assert(els.has(id),id);return els.get(id)},createElement:t=>new E(t),head:{append(s){vm.runInContext(fs.readFileSync(path.join(folder,s.src.split('?')[0]),'utf8'),scope);s.onload()}}};
scope=vm.createContext({document,devicePixelRatio:1,window:{addEventListener(){}},setInterval(){}});
vm.runInContext(html.split('<script>')[1].split('</script>')[0],scope);
assert(els.get('rows').children.length>=2);assert(paints>20);assert(els.get('proposal').src.endsWith('viewer.html'));
for(const [k,v]of Object.entries({minimum:1000,maximum:2000,points:25,generations:2,population:4,spacing:'log'}))els.get(k).value=String(v);
els.get('command-button').onclick();assert(els.get('command').textContent.includes('--frequency-points 25'));
els.get('minimum').value='3000';els.get('command-button').onclick();assert(els.get('command').textContent.includes('positive increasing'));
const state=JSON.parse(fs.readFileSync(path.join(folder,'campaign.json'),'utf8'));
state.generations[0].candidates[0].score={objective:1.2,terms:{horizontal:.4,vertical:2}};state.generations[0].candidates[0].rank=1;
scope.window.concordCampaign(state);assert(els.get('rows').children[0].children[0].textContent===1);
console.log('Campaign viewer: selection, ranked/unranked charts, finite coordinates and command controls passed.');
