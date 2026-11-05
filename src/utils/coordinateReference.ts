import proj4, {type Converter} from 'proj4';
import parameters from '../../sas_planet_py/nord_sahara_params.json';
export interface ProjectedCoordinate {zone:number;hemisphere:'N'|'S';easting:number;northing:number;epsg:number;}
const transforms=new Map<string,Converter>();
function transform(definition:string,lon:number,lat:number):[number,number]{
  let converter=transforms.get(definition);
  if(!converter){converter=proj4('EPSG:4326',definition);transforms.set(definition,converter);}
  return converter.forward([lon,lat]) as [number,number];
}
export function utmZone(lat:number,lon:number){
  let zone=Math.min(60,Math.max(1,Math.floor((lon+180)/6)+1));
  if(lat>=56&&lat<64&&lon>=3&&lon<12)zone=32;
  if(lat>=72&&lat<84&&lon>=0&&lon<42)zone=lon<9?31:lon<21?33:lon<33?35:37;
  return zone;
}
export function projectWgsUtm(lat:number,lon:number):ProjectedCoordinate|null {
  if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat< -80||lat>84||lon< -180||lon>180)return null;
  const zone=utmZone(lat,lon),hemisphere=lat>=0?'N':'S';
  const [easting,northing]=transform('+proj=utm +zone='+zone+(hemisphere==='S'?' +south':'')+' +datum=WGS84 +units=m +no_defs',lon,lat);
  return {zone,hemisphere,easting,northing,epsg:(hemisphere==='N'?32600:32700)+zone};
}
export function projectNordSahara(lat:number,lon:number,forcedZone=0):ProjectedCoordinate|null {
  const [west,south,east,north]=parameters.bbox;
  if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat<south||lat>north||lon<west||lon>=east)return null;
  const zone=forcedZone||utmZone(lat,lon);
  if(!parameters.zones.includes(zone))return null;
  const definition='+proj=utm +zone='+zone+' +a='+parameters.a+' +rf='+parameters.rf+' +towgs84='+parameters.towgs84.join(',')+' +units=m +no_defs';
  const [easting,northing]=transform(definition,lon,lat);
  return {zone,hemisphere:'N',easting,northing,epsg:30700+zone};
}
export function projectedText(value:ProjectedCoordinate,prefix='UTM'){
  return prefix+' '+value.zone+value.hemisphere+' · E '+value.easting.toFixed(2)+' · N '+value.northing.toFixed(2)+' m';
}
