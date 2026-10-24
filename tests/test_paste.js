const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('anviroute/dashboard.py','utf8');
const script = source.split('<script>')[1].split('</script>')[0].replace('__TOKEN__','"test-token"');
new vm.Script(script);
const parser = script.slice(script.indexOf('function parseSession('),script.indexOf("$('session').oninput"));
const parse = new Function(parser+';return parseSession;')();
const url='https://example.trycloudflare.com/v1';
const key='test-secret_1234567890';
for(const input of [
 `Base URL: ${url}\nAPI key: ${key}\nModel: qwen`,
 `${url}\n${key}`, `${url} ${key}`,
 `URL: ${url}\nAPI_KEY=${key}`, `URL: ${url}\nToken: ${key}`,
 `**Base URL:** ${url}\n**API key:** "${key}"`,
 JSON.stringify({base_url:url,api_key:key,model:'qwen'}),
 `curl '${url}' -H 'Authorization: Bearer ${key}'`,
 `Base URL: ${url}\nAPI key: Bearer ${key}`,
]){const p=parse(input);assert.equal(p.url,url,input);assert.equal(p.key,key,input);assert.equal(p.error,undefined,input);}
assert.equal(parse(key).key,key);
assert.equal(parse(url).key,undefined);
assert.ok(parse(`Base URL: ${url}\nAPI key:`).error);
assert.ok(parse('random unrelated text').error);
assert.ok(parse(`${key}\nanother-secret_1234567890`).error);
assert.equal(parse(`Base URL: ${url}\nAPI key: "${key}"`).key,key);
assert.equal(parse('').error,undefined);
console.log('Paste parser: 15 cases passed; full dashboard JavaScript syntax valid.');
