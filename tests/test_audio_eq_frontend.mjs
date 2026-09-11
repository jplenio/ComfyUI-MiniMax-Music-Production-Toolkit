// No browser dependencies: mathematical frontend/backend parity and JSON roundtrip.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { coefficients, response, readSettings, TYPES } from "../web/eq_dsp.js";

const cases = [];
for (const sr of [8000, 44100, 48000, 96000]) {
    for (const type of TYPES) {
        for (const gain of [-12, 0, 12]) {
            const band = {id:"b", enabled:true, type, frequency_hz:Math.min(1200,sr*.4),gain_db:gain,q:.7,slope:.5};
            cases.push({sr,band});
        }
    }
}
const script = `
import sys,json,types,pathlib
p=types.ModuleType('eq_parity');p.__path__=[str(pathlib.Path('.').resolve())];sys.modules['eq_parity']=p
from eq_parity.eq_config import band_sos
print(json.dumps([band_sos(c['band'],c['sr']).tolist() for c in json.load(sys.stdin)]))
`;
const python = spawnSync(process.env.PYTHON ?? "python", ["-B", "-c", script], {input:JSON.stringify(cases),encoding:"utf8"});
assert.equal(python.status,0,python.stderr);
const expected = JSON.parse(python.stdout);
cases.forEach((c,i) => coefficients(c.band,c.sr).forEach((v,j)=>assert.ok(Math.abs(v-expected[i][j])<1e-12)));
const settings={schema:"minimax_eq_v1",preamp_db:0,bands:[{id:"b",enabled:true,type:"peak",frequency_hz:1000,gain_db:6,q:1}]};
assert.ok(Math.abs(response(settings,48000,[1000])[0]-6)<1e-9);
assert.deepEqual(readSettings(JSON.stringify(settings)),settings);
assert.throws(()=>readSettings('{"schema":"wrong","bands":[]}'));
console.log(`${cases.length} EQ coefficient cases match Python; response and serialization passed.`);
