import {useCallback,useReducer} from 'react';
export type History<T>={past:T[];present:T;future:T[]};
export function historyReducer<T>(state:History<T>,action:{type:'set';value:T|((v:T)=>T)}|{type:'undo'|'redo'}):History<T>{
 if(action.type==='undo')return state.past.length?{past:state.past.slice(0,-1),present:state.past.at(-1)!,future:[state.present,...state.future]}:state;
 if(action.type==='redo')return state.future.length?{past:[...state.past,state.present],present:state.future[0],future:state.future.slice(1)}:state;
 if(action.type!=='set')return state;const value=typeof action.value==='function'?(action.value as (v:T)=>T)(state.present):action.value;if(value===state.present)return state;
 const past=[...state.past,state.present].slice(-50);let bytes=past.reduce((n,v)=>n+JSON.stringify(v).length,0);while(past.length>1&&bytes>32000000)bytes-=JSON.stringify(past.shift()).length;
 return {past,present:value,future:[]};
}
export function useHistoryState<T>(initial:T|(()=>T)){const [state,dispatch]=useReducer(historyReducer<T>,undefined,()=>({past:[],present:typeof initial==='function'?(initial as ()=>T)():initial,future:[]}));const set=useCallback((value:T|((v:T)=>T))=>dispatch({type:'set',value}),[]);return {value:state.present,set,undo:()=>dispatch({type:'undo'}),redo:()=>dispatch({type:'redo'}),canUndo:!!state.past.length,canRedo:!!state.future.length};}
