import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);const api=require('../../dist/index.umd.js');
const {ApiRequestError,withholdsVoteOutput,eligibleVoteCandidates,getSeatCoordinates,latestAttemptEvents,mapPublicOutputEvents,mergePublicOutputEvents,normalizeCurrentRoundUpstream,normalizePanelParams,normalizeUndercoverGameViewModel,parsePrivateActionContext,publicEventFromNodeDetail,requestJson,serializeVoteAbstain,serializeVoteTarget,spriteUrl,sprites,truncateBubbleText,unicodeLength,validateSpeech}=api;
assert.equal(api.joinUrl('/api/','state-machine-runs'),'/api/state-machine-runs');
assert.deepEqual(api.unwrapEnvelope({code:20000,request_id:'r',data:{ok:true}}),{ok:true});
await assert.rejects(requestJson('/bcnproxy','/pending-human-nodes',{},async()=>new Response('<!DOCTYPE html><html>PRIVATE_PAGE</html>',{status:200,headers:{'content-type':'text/html'}})),e=>e instanceof ApiRequestError&&/JSON/.test(e.message)&&!/PRIVATE_PAGE|find/.test(e.message));
await assert.rejects(requestJson('/api','/conflict',{},async()=>new Response(JSON.stringify({message:'expired'}),{status:409})),e=>e instanceof ApiRequestError&&e.conflict);
const params=normalizePanelParams({runId:'run-example',groupId:'group-example',sessionId:'session-example',gameSessionId:'game-example',phase:'voting',round:2,attempt:2,host:{actorId:'host',displayName:'Host'},seatOrder:['a','b','c'],turnOrder:['a','b'],players:[{actorId:'a',displayName:'A',seatNumber:1,isHuman:true},{actorId:'b',displayName:'B',seatNumber:2},{actorId:'c',displayName:'C',seatNumber:3,alive:false}],nodeActorMap:{'node-a':'a','node-b':'b','node-host':'host','node-host-2':'host'},currentViewerActorId:'a',currentAction:{actorId:'a',type:'vote',nodeId:'node-a'},rules:{speechMaxChars:25,forbidOwnWord:true},publicHistory:[{round:1,speeches:[{actorId:'c',seatNumber:3,displayName:'C',text:'older clue'}]}],voteCandidates:[{actorId:'b',displayName:'B',seatNumber:2,eligible:true},{actorId:'c',displayName:'C',seatNumber:3,eligible:true,eliminated:true}]});
assert.equal(params.apiBaseUrl,'/bcnproxy');assert.deepEqual(params.turnOrder,['a','b']);assert.equal(params.players[2].seatNumber,3);assert.equal(params.publicHistory[0].speeches[0].text,'older clue');assert.deepEqual(eligibleVoteCandidates(params.voteCandidates).map(x=>x.actorId),['b']);assert.deepEqual(getSeatCoordinates(params.seatOrder).map(x=>x.actorId),['a','b','c']);assert.deepEqual(truncateBubbleText('你好世界',3),{text:'你好…',truncated:true});
const wallSprite=decodeURIComponent(spriteUrl(sprites.wall));const floorSprite=decodeURIComponent(spriteUrl(sprites.floor));const tableSprite=decodeURIComponent(spriteUrl(sprites.table));assert.match(wallSprite,/viewBox="0 0 32 32"/);assert.match(floorSprite,/viewBox="32 0 32 32"/);assert.match(tableSprite,/viewBox="96 0 32 32"/);assert.notEqual(wallSprite,floorSprite);
const legacy=normalizePanelParams({runId:'r',groupId:'g',sessionId:'s',phase:'speaking',round:1,host:{actorId:'h',displayName:'H'},seatOrder:['a'],players:[{actorId:'a',displayName:'A',publicFields:{seat:7}}],nodeActorMap:{}});assert.equal(legacy.players[0].seatNumber,7);assert.deepEqual(legacy.turnOrder,['a']);
const instruction=`human text\n[UNDERCOVER_UI_CONTEXT_V1]\n{"action":"speech","round":2,"seatNumber":1,"word":"秘密词","maxChars":5,"forbidOwnWord":true,"bluntness":3}\n[/UNDERCOVER_UI_CONTEXT_V1]`;
assert.deepEqual(parsePrivateActionContext(instruction).context,{version:1,action:'speech',round:2,seatNumber:1,word:'秘密词',maxChars:5,forbidOwnWord:true,bluntness:3});assert.equal(parsePrivateActionContext('plain').present,false);assert.match(parsePrivateActionContext('[UNDERCOVER_UI_CONTEXT_V2]\n{"word":"DO_NOT_LEAK"}').error,/不支持/);assert.doesNotMatch(parsePrivateActionContext('[UNDERCOVER_UI_CONTEXT_V1]\n{"word":"DO_NOT_LEAK"}').error,/DO_NOT_LEAK/);
assert.equal(unicodeLength('A😀中'),3);assert.deepEqual(validateSpeech('',5),{valid:false,error:'empty',count:0});assert.equal(validateSpeech('一二三四五六',5).error,'too_long');assert.equal(validateSpeech('这是秘密词',20,'秘密词',true).error,'contains_own_word');assert.equal(validateSpeech('安全描述',20,'秘密词',true).valid,true);assert.equal(serializeVoteTarget('b'),'\{"kind":"vote","target_actor_id":"b"\}'.replace('\\{','{').replace('\\}','}'));assert.equal(serializeVoteAbstain(),'{"kind":"vote","abstain":true}');
const messages=[{id:'raw-vote',sequence:1,content:'{"kind":"vote","target_actor_id":"b"}',metadata:{state_machine:{event:'output',run_id:'run-example',node_id:'node-a',attempt:1}}},{id:'host1',sequence:2,content:'opening',metadata:{state_machine:{event:'output',run_id:'run-example',node_id:'node-host',attempt:1}}},{id:'host2',sequence:3,content:'tallying',metadata:{state_machine:{event:'output',run_id:'run-example',node_id:'node-host-2',attempt:1}}},{id:'other',sequence:4,content:'other',metadata:{state_machine:{event:'output',run_id:'other',node_id:'node-a',attempt:1}}}];
const events=mapPublicOutputEvents(messages,params);assert.deepEqual(events.map(x=>x.text),['opening','tallying']);assert.doesNotMatch(JSON.stringify(events),/target_actor_id|"b"/);
const model=normalizeUndercoverGameViewModel(params,{run:{run_id:'run-example',status:'running'},nodes:[{node_id:'node-a',status:'completed',attempt:2},{node_id:'node-b',status:'running'},{node_id:'node-host',status:'completed'},{node_id:'node-host-2',status:'running'}]},[{node_id:'node-a',attempt:2,instruction,upstream_artifacts:[{node_id:'x',text:'prior clue'}]}],messages);
assert.deepEqual(model.actors.filter(x=>x.kind==='player').map(x=>x.actor.actorId),['a','b','c']);assert.equal(model.actors.find(x=>x.actor.actorId==='c').state,'eliminated');assert.equal(model.actors.find(x=>x.kind==='host').latestOutput.text,'tallying');assert.equal(model.pendingHumanActorId,'a');assert.equal(model.totalTurns,2);assert.equal(model.completedTurns,1);assert.equal(model.actors.find(x=>x.actor.actorId==='c').publicHistory[0].text,'older clue');
assert.throws(()=>normalizePanelParams({phase:'speaking',round:1}),/runId is required/);

const speakingParams={...params,phase:'speaking'};
const normalizedUpstream=normalizeCurrentRoundUpstream([
  {node_id:'node-host',text:'主持人开场'},
  {node_id:'node-b',text:'二号先说'},
  {node_id:'unknown',text:'未知节点'},
  {node_id:'speak_open',text:'入口节点'},
  {node_id:'node-a',text:'一号后返回但应排前'},
  {node_id:'collect',text:'汇总节点'},
],speakingParams);
assert.deepEqual(normalizedUpstream.map(x=>`${x.seatNumber}号 ${x.displayName}：${x.text}`),['1号 A：一号后返回但应排前','2号 B：二号先说']);

const speechDetail=publicEventFromNodeDetail({node:{node_id:'node-a',run_id:'run-example',status:'completed',attempt:1,completed_at:10,artifact_text:'来自节点详情的公开发言'}},speakingParams);
assert.equal(speechDetail.text,'来自节点详情的公开发言');
assert.equal(speechDetail.source,'node-detail');
const voteDetail=publicEventFromNodeDetail({node:{node_id:'node-b',run_id:'run-example',status:'completed',attempt:1,artifact_text:'{"kind":"vote","target_actor_id":"a"}'}},params);
assert.equal(voteDetail.text,'已投票');
const graphOnlyVote=publicEventFromNodeDetail({node:{node_id:'node-b',run_id:'run-example',status:'completed',attempt:1}},params);
assert.equal(graphOnlyVote.text,'已投票','an unfetched ballot still shows as cast from graph status');
// Ballots are withheld until the named tally node completes (#2609 phase 1).
const tallyParams=normalizePanelParams({...params,voteTallyNodeId:'node-host'});
const castB={node_id:'node-b',status:'completed'};
assert.equal(withholdsVoteOutput(castB,[castB,{node_id:'node-host',status:'running'}],tallyParams),true);
assert.equal(withholdsVoteOutput(castB,[castB,{node_id:'node-host',status:'completed'}],tallyParams),false,'released once the tally completes');
assert.equal(withholdsVoteOutput({node_id:'node-host',status:'completed'},[],tallyParams),false,'host output is never withheld');
assert.equal(withholdsVoteOutput(castB,[castB],params),false,'without voteTallyNodeId the legacy behaviour is unchanged');
assert.equal(withholdsVoteOutput(castB,[castB],normalizePanelParams({...tallyParams,phase:'speaking'})),false,'speech is never withheld');
assert.throws(()=>normalizePanelParams({...params,voteTallyNodeId:'node-b'}),/voteTallyNodeId must name a host node/);
assert.equal(publicEventFromNodeDetail({node:{node_id:'node-a',run_id:'run-example',status:'completed',attempt:1}},speakingParams),undefined,'speech without text stays hidden');
assert.doesNotMatch(JSON.stringify(voteDetail),/target_actor_id|"a"/);
assert.equal(publicEventFromNodeDetail({node:{node_id:'node-a',run_id:'other-run',status:'completed',artifact_text:'stale secret'}},speakingParams),undefined);

const older={...speechDetail,identity:'game-example:run-example:node-a:1',attempt:1,text:'旧尝试'};
const newer={...speechDetail,identity:'game-example:run-example:node-a:2',attempt:2,text:'新尝试'};
const merged=latestAttemptEvents(mergePublicOutputEvents([older],[newer]));
assert.deepEqual(merged.map(x=>x.text),['新尝试']);
const detailModel=normalizeUndercoverGameViewModel(speakingParams,{run:{run_id:'run-example',status:'running'},nodes:[{node_id:'node-a',status:'completed',attempt:2}]},[],[],[older,newer]);
assert.equal(detailModel.actors.find(x=>x.actor.actorId==='a').latestOutput.text,'新尝试');

// #2609 multi-Human: private word from Group Context; the readable entry also identifies the viewer's seat.
{
  const {resolvePrivateWord,privateWordContextName,parsePrivateWordContent,sceneSeatGeometry}=api;
  const players=[{actorId:'h1',displayName:'H1',seatNumber:1,isHuman:true},{actorId:'b2',displayName:'B2',seatNumber:2},{actorId:'h3',displayName:'H3',seatNumber:3,isHuman:true}];
  const multi=normalizePanelParams({runId:'r',groupId:'g',sessionId:'g:s',phase:'speaking',round:1,host:{actorId:'host',displayName:'Host'},seatOrder:['h1','b2','h3'],players,nodeActorMap:{},privateWord:{contextKey:'0123abcd0123abcd',scopeLevel:'session'}});
  assert.deepEqual(multi.privateWord,{contextKey:'0123abcd0123abcd',scopeLevel:'session'});
  assert.throws(()=>normalizePanelParams({...multi,privateWord:{contextKey:'../x',scopeLevel:'session'}}),/privateWord/);
  assert.throws(()=>normalizePanelParams({...multi,privateWord:{contextKey:'0123abcd',scopeLevel:'group'}}),/privateWord/);
  assert.equal(privateWordContextName('0123abcd0123abcd',3),'word_0123abcd0123abcd_seat3');
  assert.equal(parsePrivateWordContent('你的词语是：灯塔'),'灯塔');assert.equal(parsePrivateWordContent('灯塔'),undefined);
  // The viewer owns seat 3: seat 1 answers 403, seat 3 answers its entry; only Human seats are probed.
  const asked=[];const own=(items)=>async(url,init)=>{const body=JSON.parse(init.body);asked.push({url,name:body.name,scopes:body.scope_levels,method:init.method});if(body.name.endsWith('_seat3'))return new Response(JSON.stringify({items}),{status:200});return new Response(JSON.stringify({status:'permission_denied'}),{status:403})};
  const word=await resolvePrivateWord(multi,undefined,own([{name:'word_0123abcd0123abcd_seat3',scope_level:'session',content:'你的词语是：灯塔'}]));
  assert.deepEqual(word,{seatNumber:3,actorId:'h3',word:'灯塔'});
  assert.deepEqual(asked.map(x=>x.name),['word_0123abcd0123abcd_seat1','word_0123abcd0123abcd_seat3']);
  assert.ok(asked.every(x=>x.method==='POST'&&x.url==='/bcnproxy/groupcontext/get?groupId=g&sessionId=g%3As'&&JSON.stringify(x.scopes)==='["session"]'));
  // Decoys: wrong scope, wrong name, or more than one item are never read as the word.
  for(const items of [[{name:'word_0123abcd0123abcd_seat3',scope_level:'group',content:'你的词语是：假'}],[{name:'word_x_seat3',scope_level:'session',content:'你的词语是：假'}],[{name:'word_0123abcd0123abcd_seat3',scope_level:'session',content:'你的词语是：A'},{name:'word_0123abcd0123abcd_seat3',scope_level:'session',content:'你的词语是：B'}]])assert.equal(await resolvePrivateWord(multi,undefined,own(items)),undefined);
  // Two readable entries mean something is wrong: show nothing rather than guess.
  await assert.rejects(resolvePrivateWord(multi,undefined,async(url,init)=>new Response(JSON.stringify({items:[{name:JSON.parse(init.body).name,scope_level:'session',content:'你的词语是：词'}]}),{status:200})),/不止一个/);
  // A missing route (nextgen namespace without Group Context, RFC §4.3) is reported, not hidden.
  await assert.rejects(resolvePrivateWord(multi,undefined,async()=>new Response('{}',{status:404})),/访问不到/);
  assert.equal(await resolvePrivateWord({...multi,privateWord:undefined},undefined,async()=>{throw new Error('must not fetch')}),undefined);
  // 7-8 seats spread out like the six-seat presets; six seats keep the presets.
  for(const n of [7,8])for(const c of ['wide','medium']){const seats=sceneSeatGeometry(Array.from({length:n},(_,i)=>`p${i}`),c);for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)assert.ok(Math.hypot(seats[i].x-seats[j].x,seats[i].y-seats[j].y)>=20,`${n} seats ${i}/${j} overlap`)}
  assert.deepEqual(sceneSeatGeometry(['a','b','c','d','e','f'],'wide').map(s=>[s.x,s.y]),[[72,47],[86,64],[70,83],[30,83],[14,64],[28,47]]);
}

console.log('Focused undercover-game behavior tests passed.');
