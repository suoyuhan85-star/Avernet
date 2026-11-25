import type {
  PlayerActor,
  PublicOutputEvent,
  StateMachineNode,
  StateMachineNodeDetailResponse,
  UndercoverGamePanelParams,
  UpstreamArtifact,
} from './types';

export interface LabeledUpstreamArtifact {
  nodeId: string;
  actorId: string;
  seatNumber: number;
  displayName: string;
  text: string;
}

export function normalizeCurrentRoundUpstream(
  artifacts: UpstreamArtifact[] | undefined,
  params: Pick<UndercoverGamePanelParams, 'host' | 'nodeActorMap' | 'players' | 'turnOrder'>,
): LabeledUpstreamArtifact[] {
  if (!artifacts?.length) return [];
  const players = new Map(params.players.map((player) => [player.actorId, player]));
  const turnIndex = new Map(params.turnOrder.map((actorId, index) => [actorId, index]));

  return artifacts.flatMap((artifact) => {
    const actorId = params.nodeActorMap[artifact.node_id];
    const player = actorId ? players.get(actorId) : undefined;
    const text = typeof artifact.text === 'string' ? artifact.text.trim() : '';
    if (!actorId || actorId === params.host.actorId || !player || !turnIndex.has(actorId) || !text) return [];
    return [{
      nodeId: artifact.node_id,
      actorId,
      seatNumber: player.seatNumber,
      displayName: player.displayName,
      text,
    }];
  }).sort((left, right) => {
    const order = (turnIndex.get(left.actorId) ?? Infinity) - (turnIndex.get(right.actorId) ?? Infinity);
    return order || left.seatNumber - right.seatNumber || left.nodeId.localeCompare(right.nodeId);
  });
}

export function completedMappedNodes(
  nodes: StateMachineNode[],
  params: Pick<UndercoverGamePanelParams, 'nodeActorMap'>,
): StateMachineNode[] {
  return nodes.filter((node) => node.status === 'completed' && Boolean(params.nodeActorMap[node.node_id]));
}

/**
 * During a voting phase that names its tally node, a player's ballot is not
 * published until that node completes. The panel then neither fetches nor
 * shows the ballot and renders the node as cast from its graph status alone.
 * This is a display rule only; BCS still serves node details to any Present
 * Human of the run (known limitation of #2609 phase 1).
 */
export function withholdsVoteOutput(
  node: StateMachineNode,
  nodes: StateMachineNode[],
  params: Pick<UndercoverGamePanelParams, 'phase' | 'host' | 'nodeActorMap' | 'voteTallyNodeId'>,
): boolean {
  const tally = params.voteTallyNodeId;
  if (!tally || !params.phase.toLowerCase().includes('vot') || node.node_id === tally) return false;
  const actorId = params.nodeActorMap[node.node_id];
  if (!actorId || actorId === params.host.actorId) return false;
  return !nodes.some((candidate) => candidate.node_id === tally && candidate.status === 'completed');
}

export function publicEventFromNodeDetail(
  detail: StateMachineNodeDetailResponse,
  params: Pick<UndercoverGamePanelParams, 'runId' | 'gameSessionId' | 'phase' | 'host' | 'nodeActorMap' | 'display'>,
): PublicOutputEvent | undefined {
  const node = detail.node;
  const actorId = params.nodeActorMap[node.node_id];
  const raw = node.artifact_text;
  const attempt = typeof node.attempt === 'number' && node.attempt > 0 ? node.attempt : 1;
  if (!actorId || node.run_id && node.run_id !== params.runId) return undefined;

  const voting = params.phase.toLowerCase().includes('vot');
  const isHost = actorId === params.host.actorId;
  // A ballot is shown as cast from its completed status alone; BCS withholds
  // sealed ballot text until the tally, so it may be absent here.
  if (voting && !isHost && node.status === 'completed') {
    return {
      identity: `${params.gameSessionId ?? 'phase'}:${params.runId}:${node.node_id}:${attempt}`,
      runId: params.runId,
      nodeId: node.node_id,
      attempt,
      actorId,
      text: '已投票',
      pending: false,
      timestamp: node.completed_at,
      source: 'node-detail',
    };
  }
  if (typeof raw !== 'string' || !raw.trim()) return undefined;
  if (isHost && params.display?.showHostOutput === false) return undefined;

  return {
    identity: `${params.gameSessionId ?? 'phase'}:${params.runId}:${node.node_id}:${attempt}`,
    runId: params.runId,
    nodeId: node.node_id,
    attempt,
    actorId,
    text: raw.trim(),
    pending: false,
    timestamp: node.completed_at,
    source: 'node-detail',
  };
}

export function mergePublicOutputEvents(
  messageEvents: PublicOutputEvent[],
  detailEvents: PublicOutputEvent[],
): PublicOutputEvent[] {
  const merged = new Map<string, PublicOutputEvent>();
  for (const event of [...messageEvents, ...detailEvents]) {
    const previous = merged.get(event.identity);
    if (!previous || event.source === 'node-detail' || (event.timestamp ?? -Infinity) >= (previous.timestamp ?? -Infinity)) {
      merged.set(event.identity, event);
    }
  }
  return [...merged.values()].sort((left, right) =>
    (left.sequence ?? Infinity) - (right.sequence ?? Infinity)
    || (left.timestamp ?? -Infinity) - (right.timestamp ?? -Infinity)
    || left.identity.localeCompare(right.identity));
}

export function latestAttemptEvents(events: PublicOutputEvent[]): PublicOutputEvent[] {
  const attempts = new Map<string, number>();
  for (const event of events) attempts.set(event.nodeId, Math.max(attempts.get(event.nodeId) ?? 0, event.attempt));
  return events.filter((event) => event.attempt === attempts.get(event.nodeId));
}

export function playerByActorId(players: PlayerActor[], actorId: string): PlayerActor | undefined {
  return players.find((player) => player.actorId === actorId);
}
