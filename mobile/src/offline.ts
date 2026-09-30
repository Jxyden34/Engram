import type { Memory, Session } from './api';

type Store = {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
};

export type OfflineMemory = Memory & { favorite?: boolean };
export type OfflineLibrary = { items: OfflineMemory[]; savedAt: string | null };

const PREFIX = 'engram_library_v1_';
const MAX_ITEMS = 20;
const MAX_ENCODED_LENGTH = 1800;

function scope(session: Session): string {
  return `${session.origin}\u0000${session.username}\u0000${session.projectId}`;
}

function scopeId(session: Session): string {
  const value = scope(session);
  let first = 2166136261;
  let second = 5381;
  for (let i = 0; i < value.length; i++) {
    first = Math.imul(first ^ value.charCodeAt(i), 16777619);
    second = Math.imul(second, 33) ^ value.charCodeAt(i);
  }
  return `${(first >>> 0).toString(16).padStart(8, '0')}${(second >>> 0).toString(16).padStart(8, '0')}`;
}

function indexKey(session: Session): string { return PREFIX + scopeId(session) + '_index'; }
function itemKey(session: Session, id: string): string { return PREFIX + scopeId(session) + '_' + id; }

function compact(item: OfflineMemory): OfflineMemory {
  const base = { id: item.id, title: item.title, content: item.content, memory_type: item.memory_type, updated_at: item.updated_at, ...(item.favorite ? { favorite: true } : {}), ...(item.truncated ? { truncated: true } : {}) };
  if (encodeURIComponent(JSON.stringify(base)).length <= MAX_ENCODED_LENGTH) return base;
  const characters = Array.from(item.content);
  let low = 0; let high = characters.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    const candidate = { ...base, content: characters.slice(0, middle).join('') + '…', truncated: true };
    if (encodeURIComponent(JSON.stringify(candidate)).length <= MAX_ENCODED_LENGTH) low = middle;
    else high = middle - 1;
  }
  const result = { ...base, content: characters.slice(0, low).join('') + '…', truncated: true };
  if (encodeURIComponent(JSON.stringify(result)).length > MAX_ENCODED_LENGTH) throw new Error('Memory title is too large to cache.');
  return result;
}

export async function readOfflineLibrary(store: Store, session: Session): Promise<OfflineLibrary> {
  const raw = await store.getItemAsync(indexKey(session));
  if (!raw) return { items: [], savedAt: null };
  let index: { scope: string; ids: string[]; savedAt: string };
  try { index = JSON.parse(raw) as typeof index; }
  catch { return { items: [], savedAt: null }; }
  if (index.scope !== scope(session) || !Array.isArray(index.ids) || typeof index.savedAt !== 'string') return { items: [], savedAt: null };
  const values = await Promise.all(index.ids.map(id => store.getItemAsync(itemKey(session, id))));
  const items = values.flatMap(value => {
    try { return value ? [JSON.parse(value) as OfflineMemory] : []; }
    catch { return []; }
  });
  return { items, savedAt: index.savedAt };
}

async function writeLibrary(store: Store, session: Session, previous: OfflineLibrary, items: OfflineMemory[], savedAt: string | null): Promise<OfflineLibrary> {
  for (const item of items) await store.setItemAsync(itemKey(session, item.id), JSON.stringify(item));
  await store.setItemAsync(indexKey(session), JSON.stringify({ scope: scope(session), ids: items.map(item => item.id), savedAt }));
  for (const item of previous.items) {
    if (!items.some(next => next.id === item.id)) await store.deleteItemAsync(itemKey(session, item.id));
  }
  return { items, savedAt };
}

export async function saveOfflineLibrary(store: Store, session: Session, memories: Memory[]): Promise<OfflineLibrary> {
  const previous = await readOfflineLibrary(store, session);
  const favorites = previous.items.filter(item => item.favorite).map(item => {
    const latest = memories.find(next => next.id === item.id);
    try { return latest ? compact({ ...latest, favorite: true }) : item; } catch { return item; }
  });
  const recent = memories.filter(item => !favorites.some(saved => saved.id === item.id)).flatMap(item => {
    try { return [compact(item)]; } catch { return []; }
  });
  return writeLibrary(store, session, previous, [...favorites, ...recent].slice(0, MAX_ITEMS), new Date().toISOString());
}

export async function toggleFavorite(store: Store, session: Session, memory: Memory): Promise<OfflineLibrary> {
  const previous = await readOfflineLibrary(store, session);
  const favorite = !previous.items.find(item => item.id === memory.id)?.favorite;
  if (favorite && previous.items.filter(item => item.favorite).length >= 10) throw new Error('You can keep 10 favourites per project. Remove one before adding another.');
  const item = compact({ ...memory, favorite });
  const items = [item, ...previous.items.filter(saved => saved.id !== item.id)].sort((a, b) => Number(!!b.favorite) - Number(!!a.favorite)).slice(0, MAX_ITEMS);
  return writeLibrary(store, session, previous, items, previous.savedAt || new Date().toISOString());
}

export async function clearOfflineLibrary(store: Store, session: Session): Promise<void> {
  const previous = await readOfflineLibrary(store, session);
  await store.deleteItemAsync(indexKey(session));
  for (const item of previous.items) await store.deleteItemAsync(itemKey(session, item.id));
}

export function searchOffline(items: OfflineMemory[], query: string): OfflineMemory[] {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return items.filter(item => words.every(word => `${item.title} ${item.content}`.toLocaleLowerCase().includes(word)));
}
