const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('anviroute/dashboard.py','utf8');
const scripts=[...source.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1].replace('__TOKEN__','"local-test"'));
for(const script of scripts)new vm.Script(script);
assert.ok(!source.includes('parseSession'));
assert.ok(!source.includes('Paste Kaggle output'));
class Element{
 constructor(tag='div'){this.tag=tag;this.children=[];this.value='';this.textContent='';this.classList={add(){}};this.checked=false;}
 append(...items){this.children.push(...items)} replaceChildren(...items){this.children=items}
 setAttribute(k,v){this[k]=v} contains(e){return this===e||this.children.some(c=>c.contains?.(e))}
 reportValidity(){return !!this.value} focus(){document.activeElement=this} reset(){this.value=''}
}
const elements={};const document={activeElement:null,documentElement:{dataset:{}},getElementById(id){return elements[id]??=new Element()},createElement(tag){return new Element(tag)},querySelector(){return new Element()}};
let profile={id:'one',name:'qwen',url:'https://old.example/v1',model:'qwen',format:'openai',key_saved:true};let calls=[];let savedTheme='dark';
const sandbox={document,location:{pathname:'/connections'},localStorage:{getItem(){return savedTheme},setItem(k,v){savedTheme=v}},setInterval(){return 1},clearInterval(){},setTimeout,Date,console,confirm(){return true},fetch:async(path,opts)=>{if(opts.body){const data=JSON.parse(opts.body);calls.push({path,data});if(path.endsWith('/connect'))profile={...profile,url:data.url};return {ok:true,json:async()=>({ready:true,id:'one',message:'Connected',reply:'OK',seconds:1,usage:{input_tokens:1,output_tokens:1}})}}return {ok:true,json:async()=>({providers:[profile],active:'one',address:'http://127.0.0.1:20128',version:'test',model:'qwen',ready:true,events:[],diagnostics:{}})}}};
vm.createContext(sandbox);for(const script of scripts)vm.runInContext(script,sandbox);
(async()=>{
 await new Promise(setImmediate);
 assert.equal(document.documentElement.dataset.theme,'dark');elements.theme.onclick();assert.equal(savedTheme,'light');elements.theme.onclick();assert.equal(savedTheme,'dark');
 const card=elements.providers.children[0];const fields=card.children.filter(e=>e.tag==='label').flatMap(e=>e.children);
 const url=fields.find(e=>e.type==='url'),key=fields.find(e=>e.type==='password'),save=card.children.find(e=>e.textContent==='Save & reconnect');
 assert.equal(url.value,'https://old.example/v1');assert.equal(key.value,'');
 url.value='https://new.example/v1';key.value='new-secret';document.activeElement=key;
 await vm.runInContext('refresh()',sandbox);assert.equal(elements.providers.children[0],card);assert.equal(key.value,'new-secret');
 await save.onclick();assert.equal(calls.at(-1).data.url,'https://new.example/v1');assert.equal(calls.at(-1).data.key,'new-secret');assert.equal(calls.at(-1).data.id,'one');assert.equal(key.value,'');
 await save.onclick();assert.equal(calls.at(-1).data.key,'');
 url.value='';const before=calls.length;await save.onclick();assert.equal(calls.length,before);
 console.log('Dashboard passed: separate fields, exact key submission, blank-key preservation, invalid URL guard, polling preserves edits, persistent theme toggle.');
})().catch(e=>{console.error(e);process.exitCode=1});
