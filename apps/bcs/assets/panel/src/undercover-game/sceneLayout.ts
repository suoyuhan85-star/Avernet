export type RoomComposition='wide'|'medium'|'narrow';
export type Facing='front'|'rear'|'left'|'right';
export interface SceneSeatGeometry{actorId:string;x:number;y:number;facing:Facing;depth:number;chairVariant:Facing;labelAnchor:'above'|'below'|'left'|'right';bubbleAnchor:{x:number;y:number}}
export function roomComposition(width:number):RoomComposition{return width>=680?'wide':width>=460?'medium':'narrow'}
export function sceneSeatGeometry(actorIds:string[],composition:RoomComposition):SceneSeatGeometry[]{
 const wide=[[72,47,'rear'],[86,64,'left'],[70,83,'front'],[30,83,'front'],[14,64,'right'],[28,47,'rear']] as const;
 const medium=[[70,45,'rear'],[80,64,'left'],[65,83,'front'],[35,83,'front'],[20,64,'right'],[30,45,'rear']] as const;
 const source=actorIds.length===7?ellipseSeats(7,-37.5,38,23):actorIds.length===8?ellipseSeats(8,-90,40,23):composition==='wide'?wide:medium;
 return actorIds.map((actorId,index)=>{const preset=source[index]??[12+(index%3)*38,42+Math.floor(index/3)*34,'front'] as const;const [x,y,facing]=preset;return{actorId,x,y,facing,depth:Math.round(y),chairVariant:facing,labelAnchor:y>68?'below':'above',bubbleAnchor:{x,y:y-13}}});
}

/** 7-8 players (#2609): seats spread on the table ellipse, at least 20 units apart like the six-seat presets. */
function ellipseSeats(count:number,startDeg:number,rx:number,ry:number):(readonly [number,number,Facing])[]{
 return Array.from({length:count},(_,index)=>{const angle=(startDeg+index*360/count)*Math.PI/180;const x=Math.round(50+rx*Math.cos(angle));const y=Math.round(65+ry*Math.sin(angle));const facing:Facing=y<58?'rear':y>74?'front':x>50?'left':'right';return [x,y,facing] as const});
}
