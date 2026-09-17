import assert from 'node:assert/strict';
import { modelTemplate, connectedModel, prepareCoverAudioWidgets } from '../web/song_model_utils.js';

// Core audio upload initializes the preview immediately. Mimic that dependency
// to catch a missing preview or incorrect construction order before shipping.
function coverDefinition(name = 'MusicCoverSource') {
    return {name, input: {required: {
        model_profile_json: ['STRING', {forceInput: true}],
        audio: [['<select audio>'], {audio_upload: true}],
        mode: [['full', 'melody'], {}],
        sheetsage2_model: ['STRING', {}],
        lyrics_mode: [['new lyrics', 'original lyrics', 'instrumental'], {}],
        lead_instrument: [['Lead synth'], {}],
    }}, input_order: {required: ['model_profile_json', 'audio', 'mode', 'sheetsage2_model', 'lyrics_mode', 'lead_instrument']}};
}
function coreUploadHook(data) { data.input.required.upload = ['AUDIOUPLOAD', {}]; }
function constructWidgets(data) {
    const widgets = [];
    for (const [name, [type]] of Object.entries(data.input.required)) {
        if (type === 'AUDIOUPLOAD') widgets.find(w => w.name === 'audioUI').element.src = 'preview';
        widgets.push({name, element: {}, serialize: !['AUDIO_UI', 'AUDIOUPLOAD'].includes(type)});
    }
    return widgets;
}
const broken = coverDefinition();
coreUploadHook(broken);
assert.throws(() => constructWidgets(broken), TypeError);
for (const coreFirst of [true, false]) {
    const data = coverDefinition();
    if (coreFirst) coreUploadHook(data);
    prepareCoverAudioWidgets(data);
    if (!coreFirst) coreUploadHook(data);
    const widgets = constructWidgets(data);
    assert.equal(widgets.find(w => w.name === 'audioUI').element.src, 'preview');
    assert.deepEqual(widgets.filter(w => w.serialize).map(w => w.name),
        ['model_profile_json', 'audio', 'mode', 'sheetsage2_model', 'lyrics_mode', 'lead_instrument']);
    if (coreFirst) assert.deepEqual(data.input_order.required, Object.keys(data.input.required));
    prepareCoverAudioWidgets(data);
    assert.equal(Object.keys(data.input.required).filter(n => n === 'audioUI').length, 1);
}
const other = coverDefinition('LoadAudio');
const untouched = structuredClone(other);
prepareCoverAudioWidgets(other);
assert.deepEqual(other, untouched);
assert.equal(modelTemplate('minimax-music3-cinematic.txt','YuE2'),'yue2/cinematic.txt');
assert.equal(modelTemplate('minimax-music3-cinematic.txt','YuE2 Cover'),'yue2/cinematic.txt');
assert.equal(modelTemplate('yue2/production.txt','YuE2 Cover'),'yue2/production.txt');
assert.equal(modelTemplate('yue2/cinematic.txt','MiniMax Music 3'),'minimax-music3-cinematic.txt');
assert.equal(modelTemplate('_custom/mine.txt','YuE2'),'_custom/mine.txt');
assert.equal(modelTemplate('yue2/production.txt','YuE2'),'yue2/production.txt');
assert.equal(connectedModel({inputs:[{name:'model_profile_json',link:1}],graph:{links:{1:{origin_id:2}},getNodeById:()=>({widgets:[{name:'model',value:'YuE2'}]})}}),'YuE2');
assert.equal(connectedModel({}),undefined);
console.log('Song model frontend helpers OK');
