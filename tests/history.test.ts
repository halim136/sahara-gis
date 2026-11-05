import {test} from 'node:test';
import assert from 'node:assert/strict';
import {historyReducer,type History} from '../src/utils/history';
test('vector history restores edits and drops redo on a new branch',()=>{
 let s:History<number>={past:[],present:1,future:[]};s=historyReducer(s,{type:'set',value:2});s=historyReducer(s,{type:'set',value:v=>v+1});s=historyReducer(s,{type:'undo'});assert.equal(s.present,2);s=historyReducer(s,{type:'redo'});assert.equal(s.present,3);s=historyReducer(s,{type:'undo'});s=historyReducer(s,{type:'set',value:4});assert.deepEqual(s.future,[]);assert.equal(s.present,4);
});
test('history is bounded to fifty saved edits',()=>{let s:History<number>={past:[],present:0,future:[]};for(let i=1;i<=80;i++)s=historyReducer(s,{type:'set',value:i});assert.equal(s.past.length,50);});
