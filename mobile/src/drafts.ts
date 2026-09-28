import type { Session } from './api';

export type CaptureDraft = {
  id: string;
  origin: string;
  username: string;
  projectId: string;
  title: string;
  content: string;
  createdAt: string;
};

type Store = {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
};

const INDEX = 'engram_capture_index_v1';
const PREFIX = 'engram_capture_';
const MAX_DRAFTS = 30;
const MAX_ENCODED_LENGTH = 1800;

async function ids(store: Store): Promise<string[]> {
  const value = await store.getItemAsync(INDEX);
  return value ? JSON.parse(value) as string[] : [];
}

export function newDraft(session: Session, title: string, content: string): CaptureDraft {
  const body = content.trim() || title.trim();
  return {
    id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`,
    origin: session.origin,
    username: session.username,
    projectId: session.projectId,
    title: title.trim() || body.split('\n')[0].slice(0, 100),
    content: body,
    createdAt: new Date().toISOString(),
  };
}

export async function readDrafts(store: Store): Promise<CaptureDraft[]> {
  const entries = await Promise.all((await ids(store)).map(id => store.getItemAsync(PREFIX + id)));
  return entries.filter((value): value is string => !!value).map(value => JSON.parse(value) as CaptureDraft)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

function serialized(draft: CaptureDraft): string {
  if (!draft.content || !draft.title || !draft.projectId) throw new Error('Enter a capture before saving.');
  const value = JSON.stringify(draft);
  if (encodeURIComponent(value).length > MAX_ENCODED_LENGTH) {
    throw new Error('This capture is too long for secure offline storage. Shorten it before saving.');
  }
  return value;
}

export async function saveDraft(store: Store, draft: CaptureDraft): Promise<void> {
  const value = serialized(draft);
  const index = await ids(store);
  if (index.length >= MAX_DRAFTS) throw new Error('Send or delete a saved draft before adding another.');
  await store.setItemAsync(PREFIX + draft.id, value);
  try { await store.setItemAsync(INDEX, JSON.stringify([...index, draft.id])); }
  catch (error) { await store.deleteItemAsync(PREFIX + draft.id); throw error; }
}

export async function updateDraft(store: Store, draft: CaptureDraft): Promise<void> {
  if (!(await ids(store)).includes(draft.id)) throw new Error('Saved draft was not found.');
  await store.setItemAsync(PREFIX + draft.id, serialized(draft));
}

export async function removeDraft(store: Store, id: string): Promise<void> {
  await store.deleteItemAsync(PREFIX + id);
  await store.setItemAsync(INDEX, JSON.stringify((await ids(store)).filter(item => item !== id)));
}

export function draftsFor(drafts: CaptureDraft[], session: Session): CaptureDraft[] {
  return drafts.filter(draft => draft.origin === session.origin && draft.username === session.username && draft.projectId === session.projectId);
}
