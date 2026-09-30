import type { MemoryRelation, MemoryVersion } from './api';

export const captureTemplates = [
  { name: 'Idea', title: 'New idea', content: 'Idea:\n\nWhy it matters:\n\nNext step:\n' },
  { name: 'Decision', title: 'Decision note', content: 'Decision:\n\nReason:\n\nAlternatives considered:\n\nFollow-up:\n' },
  { name: 'Meeting', title: 'Meeting notes', content: 'Meeting:\n\nKey points:\n\nDecisions:\n\nActions and owners:\n' },
];

export function relatedMemory(relation: MemoryRelation, currentId: string): { id: string; title: string } | null {
  if (relation.from_memory_id === currentId && relation.to_memory_id !== currentId) return { id: relation.to_memory_id, title: relation.to_title };
  if (relation.to_memory_id === currentId && relation.from_memory_id !== currentId) return { id: relation.from_memory_id, title: relation.from_title };
  return null;
}

export function versionCapture(version: MemoryVersion): { title: string; content: string } {
  const snapshot = version.snapshot;
  if (typeof snapshot?.title !== 'string' || typeof snapshot?.content !== 'string' || !snapshot.content.trim()) throw new Error('This version has no readable capture text.');
  return { title: snapshot.title.slice(0, 100), content: snapshot.content };
}
