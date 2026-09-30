import { useRef, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import type { Project } from './api';
import type { CaptureDraft } from './drafts';
import VoiceCapture from './VoiceCapture';

type Props = {
  items: CaptureDraft[]; projects: Project[]; disabled: boolean;
  title: string; content: string; onTitle: (value: string) => void; onContent: (value: string) => void;
  onBusy: (value: boolean) => void;
  onQueue: (title: string, content: string) => Promise<void>;
  onSend: (item: CaptureDraft, projectId: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

export default function Inbox({ items, projects, disabled, title, content, onTitle: setTitle, onContent: setContent, onBusy, onQueue, onSend, onDelete }: Props) {
  const [editing, setEditing] = useState<CaptureDraft | null>(null);
  const [projectId, setProjectId] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const working = useRef(false);
  const input = useRef<TextInput>(null);
  async function act(task: () => Promise<void>) {
    if (working.current || disabled) return;
    working.current = true; setBusy(true); onBusy(true); setError(''); setMessage('');
    try { await task(); } catch (e) { setError(String((e as Error).message || e)); }
    finally { working.current = false; setBusy(false); onBusy(false); }
  }
  const blocked = busy || disabled;
  return <>
    <Text style={styles.heading}>Inbox</Text>
    <Text style={styles.hint}>Catch a thought now. Choose a project later. These items stay securely on this device for this server and account until you explicitly save them to Engram. They are not included in Search or Ask yet.</Text>
    <TextInput ref={input} style={[styles.input, { minHeight: 130 }]} value={content} onChangeText={setContent} multiline maxLength={1200} editable={!blocked} placeholder="A rough thought, an idea, something to sort later…" placeholderTextColor="#718094" accessibilityLabel="Inbox quick thought" />
    <TextInput style={styles.input} value={title} onChangeText={setTitle} maxLength={100} editable={!blocked} placeholder="Title (optional)" placeholderTextColor="#718094" accessibilityLabel="Inbox title" />
    <VoiceCapture content={content} onContent={setContent} onKeyboard={() => input.current?.focus()} disabled={blocked} />
    <Pressable style={styles.button} disabled={blocked || (!title.trim() && !content.trim())} accessibilityRole="button" onPress={() => act(async () => {
      await onQueue(title, content); setTitle(''); setContent(''); setMessage('Kept in your device Inbox.');
    })}><Text style={styles.link}>Keep in Inbox</Text></Pressable>
    {!!error && <Text style={styles.error}>{error}</Text>}{!!message && <Text style={styles.hint}>{message}</Text>}
    <Text style={[styles.heading, { marginTop: 28 }]}>{items.length} waiting to organise</Text>
    {!items.length && <Text style={styles.hint}>Your Inbox is clear. Add a thought above to start.</Text>}
    {items.map(item => <View key={item.id} style={styles.card}>
      {editing?.id === item.id ? <>
        <TextInput style={styles.input} value={editing.title} onChangeText={value => setEditing({ ...editing, title: value })} editable={!blocked} maxLength={100} accessibilityLabel="Review Inbox title" />
        <TextInput style={[styles.input, { minHeight: 130 }]} value={editing.content} onChangeText={value => setEditing({ ...editing, content: value })} editable={!blocked} maxLength={1200} multiline accessibilityLabel="Review Inbox content" />
        <Text style={styles.hint}>Choose the destination project:</Text>
        <View style={styles.projects}>{projects.map(project => <Pressable key={project.id} style={[styles.chip, projectId === project.id && styles.selected]} disabled={blocked} accessibilityRole="button" accessibilityState={{ selected: projectId === project.id }} onPress={() => setProjectId(project.id)}><Text style={styles.link}>{project.name}</Text></Pressable>)}</View>
        {!projects.length && <Text style={styles.hint}>Connect to load your available projects. The item stays in your Inbox.</Text>}
        <Pressable style={styles.button} disabled={blocked || !projectId || !editing.title.trim() || !editing.content.trim()} accessibilityRole="button" onPress={() => act(async () => {
          const name = projects.find(project => project.id === projectId)?.name;
          await onSend(editing, projectId); setEditing(null); setProjectId(''); setMessage(`Saved to ${name || 'the selected project'}.`);
        })}><Text style={styles.link}>Save to {projects.find(project => project.id === projectId)?.name || 'chosen project'}</Text></Pressable>
        <Pressable style={styles.button} disabled={blocked} accessibilityRole="button" onPress={() => { setEditing(null); setProjectId(''); }}><Text style={styles.link}>Cancel review</Text></Pressable>
      </> : <>
        <Text style={styles.heading}>{item.title}</Text><Text style={styles.content}>{item.content}</Text><Text style={styles.hint}>{new Date(item.createdAt).toLocaleString()} · not assigned to a project</Text>
        <Pressable style={styles.button} disabled={blocked} accessibilityRole="button" onPress={() => { setEditing({ ...item }); setProjectId(''); }}><Text style={styles.link}>Review & choose project</Text></Pressable>
      </>}
      <Pressable style={styles.button} disabled={blocked} accessibilityRole="button" onPress={() => Alert.alert('Delete Inbox item?', 'This removes the only local copy.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => void act(async () => { await onDelete(item.id); if (editing?.id === item.id) setEditing(null); }) }])}><Text style={styles.link}>Delete</Text></Pressable>
    </View>)}
  </>;
}

const styles = StyleSheet.create({
  heading: { color: '#f2f7ff', fontSize: 20, fontWeight: '800', marginBottom: 12 }, hint: { color: '#96a9bf', lineHeight: 20, marginVertical: 10 },
  input: { backgroundColor: '#182637', color: '#f2f7ff', borderWidth: 1, borderColor: '#30465c', borderRadius: 14, padding: 15, fontSize: 16, marginBottom: 8 },
  button: { padding: 14, borderRadius: 13, borderWidth: 1, borderColor: '#416887', marginTop: 12, alignItems: 'center' }, link: { color: '#7ccaff', fontWeight: '800' },
  content: { color: '#dce9f5', fontSize: 16, lineHeight: 25 }, error: { color: '#ff9b9b', marginVertical: 12 },
  card: { backgroundColor: '#172536', borderWidth: 1, borderColor: '#2b4157', borderRadius: 16, padding: 17, marginTop: 20 },
  projects: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, chip: { padding: 12, borderRadius: 12, backgroundColor: '#22344a' }, selected: { backgroundColor: '#345a7a' },
});
