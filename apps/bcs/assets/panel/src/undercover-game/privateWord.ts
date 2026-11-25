import { ApiRequestError, requestJson } from './api';
import type { UndercoverGamePanelParams } from './types';

/**
 * Multi-Human games (#2609): each Human's word lives in a session-level Group
 * Context entry readable only by the referee and that Human.
 *
 * The panel probes the entry of every Human seat with the caller's own
 * authenticated identity. Exactly one is readable; the others answer 403 and
 * carry no content. That single readable entry gives both the word and the
 * viewer's seat, so no viewer-specific value has to be published in the card
 * that every Human receives. The entry name is exact and the scope is locked to
 * `session`; anything other than exactly one item is rejected, so a decoy entry
 * planted under another name or scope is never read as the word.
 */
export interface PrivateWord {
  seatNumber: number;
  actorId: string;
  word: string;
}

interface GroupContextGetItem {
  name?: string;
  scope_level?: string;
  content?: string;
}

const CONTENT_PREFIX = '你的词语是：';

export function privateWordContextName(contextKey: string, seatNumber: number): string {
  return `word_${contextKey}_seat${seatNumber}`;
}

export function parsePrivateWordContent(content: unknown): string | undefined {
  if (typeof content !== 'string' || !content.startsWith(CONTENT_PREFIX)) return undefined;
  const word = content.slice(CONTENT_PREFIX.length).trim();
  return word || undefined;
}

export class PrivateWordError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PrivateWordError';
  }
}

export async function resolvePrivateWord(
  params: Pick<UndercoverGamePanelParams, 'privateWord' | 'players' | 'groupId' | 'sessionId' | 'apiBaseUrl'>,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<PrivateWord | undefined> {
  const config = params.privateWord;
  if (!config) return undefined;
  const query = `?groupId=${encodeURIComponent(params.groupId)}&sessionId=${encodeURIComponent(params.sessionId)}`;
  const found: PrivateWord[] = [];
  for (const player of params.players.filter((p) => p.isHuman)) {
    const name = privateWordContextName(config.contextKey, player.seatNumber);
    let body: { items?: GroupContextGetItem[] } | undefined;
    try {
      body = await requestJson<{ items?: GroupContextGetItem[] }>(params.apiBaseUrl ?? '', `/groupcontext/get${query}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ name, scope_levels: [config.scopeLevel] }),
        signal,
      }, fetchImpl);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw error;
      // Another Human's entry: readable by its owner only.
      if (error instanceof ApiRequestError && error.status === 403) continue;
      if (error instanceof ApiRequestError && error.status === 404) {
        throw new PrivateWordError('当前环境的副屏访问不到私有词接口，请联系维护者。');
      }
      throw new PrivateWordError('读取你的词失败，请稍后刷新。');
    }
    const items = (body?.items ?? []).filter((item) => item.name === name && item.scope_level === config.scopeLevel);
    if (items.length !== 1) continue;
    const word = parsePrivateWordContent(items[0].content);
    if (word) found.push({ seatNumber: player.seatNumber, actorId: player.actorId, word });
  }
  if (found.length > 1) throw new PrivateWordError('读到了不止一个词，已停止显示，请联系主持人。');
  return found[0];
}
