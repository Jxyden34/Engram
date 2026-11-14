import { colors } from './theme';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import type { Memory, MemoryRelation, MemoryVersion } from './api';
import { relatedMemory, versionCapture } from './memoryTools';

type Props = {
  memory: Memory;
  request: <T>(path: string) => Promise<T>;
  onOpen: (memory: Memory) => void;
  onCapture: (title: string, content: string) => Promise<void>;
  disabled: boolean;
};

export default function MemoryDetail({ memory, request, onOpen, onCapture, disabled }: Props) {
  const [versions, setVersions] = useState<MemoryVersion[] | null>(null);
  const [relations, setRelations] = useState<MemoryRelation[] | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  const working = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  async function act(task: () => Promise<void>) {
    if (working.current || disabled) return;
    working.current = true; setBusy(true); setError('');
    try { await task(); }
    catch (error) { if (mounted.current) setError(String((error as Error).message || error)); }
    finally { working.current = false; if (mounted.current) setBusy(false); }
  }

  return <>
    <Text style={styles.title}>{memory.title}</Text>
    <Text style={styles.meta}>{memory.memory_type} · updated {new Date(memory.updated_at).toLocaleString()}</Text>
    {memory.truncated && <Text style={styles.hint}>Saved excerpt. Fetch the full memory to read everything.</Text>}
    <Text style={styles.content}>{memory.content}</Text>
    <Pressable style={styles.button} disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
      const full = await request<Memory>(`/api/v1/memories/${memory.id}`);
      if (mounted.current) onOpen(full);
    })}><Text style={styles.link}>Fetch full memory</Text></Pressable>
    <View style={styles.actions}>
      <Pressable style={styles.button} disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
        const result = await request<MemoryVersion[]>(`/api/v1/memories/${memory.id}/versions`);
        if (mounted.current) setVersions(result);
      })}><Text style={styles.link}>Version history</Text></Pressable>
      <Pressable style={styles.button} disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
        const result = await request<MemoryRelation[]>(`/api/v1/memories/${memory.id}/relations`);
        if (mounted.current) setRelations(result);
      })}><Text style={styles.link}>Connections</Text></Pressable>
    </View>
    <Text style={styles.hint}>Full content, history and connections need a server connection.</Text>
    {!!error && <Text style={styles.error}>{error}</Text>}
    {busy && <ActivityIndicator color={colors.accent} />}
    {versions !== null && <>
      <Text style={styles.section}>Previous versions ({versions.length})</Text>
      {!versions.length && <Text style={styles.hint}>No previous edits recorded for this memory.</Text>}
      {versions.slice(0, 20).map(version => <View key={version.version_no} style={styles.card}>
        <Pressable disabled={busy || disabled} accessibilityRole="button" accessibilityState={{ expanded: expanded === version.version_no }} onPress={() => setExpanded(expanded === version.version_no ? null : version.version_no)}>
          <Text style={styles.link}>Version {version.version_no} · {new Date(version.created_at).toLocaleString()}</Text>
          <Text style={styles.meta}>{version.actor}{version.reason ? ` · ${version.reason}` : ''}</Text>
        </Pressable>
        {expanded === version.version_no && <>
          <Text style={styles.subtitle}>{version.snapshot?.title || 'Untitled version'}</Text>
          <Text style={styles.content}>{version.snapshot?.content || 'No text stored in this version.'}</Text>
          <Pressable style={styles.button} disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
            const seed = versionCapture(version);
            await onCapture(seed.title, seed.content);
          })}><Text style={styles.link}>Use version as new capture</Text></Pressable>
          <Text style={styles.hint}>Review before saving. This creates a separate memory; the current version stays in place.</Text>
        </>}
      </View>)}
      {versions.length > 20 && <Text style={styles.hint}>Showing the latest 20 previous versions.</Text>}
    </>}
    {relations !== null && <>
      <Text style={styles.section}>Connected memories</Text>
      {!relations.some(relation => relatedMemory(relation, memory.id)) && <Text style={styles.hint}>No links recorded for this memory yet.</Text>}
      {relations.map(relation => {
        const target = relatedMemory(relation, memory.id);
        return target && <Pressable key={relation.id} style={styles.card} disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
          const result = await request<Memory>(`/api/v1/memories/${target.id}`);
          if (mounted.current) onOpen(result);
        })}><Text style={styles.link}>{target.title}</Text><Text style={styles.meta}>{relation.relation_type.replaceAll('_', ' ')}</Text></Pressable>;
      })}
    </>}
  </>;
}

const styles = StyleSheet.create({
  title: { color: colors.text, fontSize: 26, fontWeight: '800', marginTop: 8, marginBottom: 10 },
  subtitle: { color: colors.text, fontSize: 18, fontWeight: '700', marginTop: 16 },
  section: { color: colors.body, fontSize: 18, fontWeight: '800', marginVertical: 18 },
  meta: { color: colors.muted, fontSize: 12, marginTop: 8 },
  content: { color: colors.body, fontSize: 16, lineHeight: 25, marginVertical: 14 },
  hint: { color: colors.muted, lineHeight: 20, marginTop: 14, marginBottom: 10 },
  error: { color: colors.danger, marginVertical: 12 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  button: { padding: 14, borderRadius: 13, borderWidth: 1, borderColor: colors.controlBorder, marginTop: 12, alignItems: 'center' },
  link: { color: colors.accent, fontWeight: '800' },
  card: { backgroundColor: colors.panel, borderWidth: 1, borderColor: colors.border, borderRadius: 16, padding: 17, marginBottom: 12 },
});
