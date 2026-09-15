import assert from 'node:assert/strict';
import { modelTemplate, connectedModel } from '../web/song_model_utils.js';
assert.equal(modelTemplate('minimax-music3-cinematic.txt','YuE2'),'yue2/cinematic.txt');
assert.equal(modelTemplate('yue2/cinematic.txt','MiniMax Music 3'),'minimax-music3-cinematic.txt');
assert.equal(modelTemplate('_custom/mine.txt','YuE2'),'_custom/mine.txt');
assert.equal(modelTemplate('yue2/production.txt','YuE2'),'yue2/production.txt');
assert.equal(connectedModel({inputs:[{name:'model_profile_json',link:1}],graph:{links:{1:{origin_id:2}},getNodeById:()=>({widgets:[{name:'model',value:'YuE2'}]})}}),'YuE2');
assert.equal(connectedModel({}),undefined);
console.log('Song model frontend helpers OK');
