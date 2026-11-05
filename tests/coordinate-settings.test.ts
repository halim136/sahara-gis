import {test} from 'node:test';
import assert from 'node:assert/strict';
import reference from './fixtures/nord_sahara_reference.json';
import {projectNordSahara,projectWgsUtm,utmZone} from '../src/utils/coordinateReference';
import {normalizeSettings,saveSettings,loadSettings} from '../src/utils/settings';
for(const point of reference.points){
 test('Nord Sahara display matches independent PROJ reference: '+point.name,()=>{
  const result=projectNordSahara(point.lat,point.lon)!;
  assert.equal(result.zone,point.zone);assert.equal(result.epsg,30700+point.zone);
  assert.ok(Math.abs(result.easting-point.easting)<.01);assert.ok(Math.abs(result.northing-point.northing)<.01);
  const wgs=projectWgsUtm(point.lat,point.lon)!;
  assert.ok(Math.abs(wgs.easting-point.wgs_easting)<.01);assert.ok(Math.abs(wgs.northing-point.wgs_northing)<.01);
 });
}
test('manual Nord Sahara zone overrides automatic zone',()=>{
 const auto=projectNordSahara(36.7538,3.0588)!,manual=projectNordSahara(36.7538,3.0588,32)!;
 assert.equal(auto.zone,31);assert.equal(manual.zone,32);assert.equal(manual.epsg,30732);assert.ok(Math.abs(auto.easting-manual.easting)>100000);
});
test('does not silently clamp unsupported locations into an Algerian zone',()=>{
 assert.equal(projectNordSahara(30,31),null);assert.equal(projectNordSahara(-30,3),null);
 assert.equal(projectNordSahara(36,3,28),null);assert.equal(projectNordSahara(NaN,3),null);
});
test('WGS84 UTM handles hemisphere, zone edges and polar limits',()=>{
 assert.equal(projectWgsUtm(-30,3)!.epsg,32731);assert.equal(utmZone(0,180),60);
 assert.equal(utmZone(60,6),32);assert.equal(utmZone(76,15),33);
 assert.equal(projectWgsUtm(85,3),null);
});
test('older settings migrate and invalid coordinate choices use defaults',()=>{
 assert.equal(normalizeSettings({theme:'dark'}).coordinateSystem,'dms');
 const value=normalizeSettings({coordinateSystem:'made-up',nordSaharaZone:28});
 assert.equal(value.coordinateSystem,'dms');assert.equal(value.nordSaharaZone,0);
});
test('coordinate system and chosen zone persist and restore',()=>{
 const original=globalThis.localStorage;const data=new Map<string,string>();
 globalThis.localStorage={get length(){return data.size;},clear:()=>data.clear(),key:index=>Array.from(data.keys())[index]??null,removeItem:key=>{data.delete(key);},getItem:key=>data.get(key)??null,setItem:(key,value)=>{data.set(key,value);}} as Storage;
 try{
  saveSettings(normalizeSettings({coordinateSystem:'utm_nord_sahara',nordSaharaZone:31}));
  assert.equal(loadSettings().coordinateSystem,'utm_nord_sahara');assert.equal(loadSettings().nordSaharaZone,31);
 }finally{globalThis.localStorage=original;}
});
