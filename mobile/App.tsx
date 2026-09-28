import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SecureStore from 'expo-secure-store';
import { api, ApiError, login, Memory, normalizeOrigin, Project, Proposal, Session } from './src/api';
import { CaptureDraft, draftsFor, newDraft, readDrafts, removeDraft, saveDraft, updateDraft } from './src/drafts';

const KEY = 'engram_mobile_session';
type Tab = 'Capture' | 'Memories' | 'Search' | 'Agent' | 'Settings';
const tabs: Tab[] = ['Capture', 'Memories', 'Search', 'Agent', 'Settings'];

export default function App() {
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [server, setServer] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [projects, setProjects] = useState<Project[]>([]);
  const [tab, setTab] = useState<Tab>('Capture');
  const [memories, setMemories] = useState<Memory[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [selected, setSelected] = useState<Memory | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Memory[] | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const composer = useRef({ title: '', content: '' });
  const editing = useRef<CaptureDraft | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const clearing = useRef<Promise<void> | null>(null);
  const [drafts, setDrafts] = useState<CaptureDraft[]>([]);
  const [captureMessage, setCaptureMessage] = useState('');
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const busyNow = useRef(false);
  const [error, setError] = useState('');
  const [scanMessage, setScanMessage] = useState('');

  function changeTitle(value: string) { composer.current.title = value; setTitle(value); }
  function changeContent(value: string) { composer.current.content = value; setContent(value); }
  function stopEditing() { editing.current = null; setEditingId(null); }

  async function storeComposer(current: Session) {
    const created = newDraft(current, composer.current.title, composer.current.content);
    const previous = editing.current;
    const item = previous ? { ...created, id: previous.id, createdAt: previous.createdAt } : created;
    if (previous) {
      await updateDraft(SecureStore, item);
    } else {
      await saveDraft(SecureStore, item);
    }
    stopEditing(); changeTitle(''); changeContent('');
    setDrafts(await readDrafts(SecureStore));
    return item;
  }

  async function keepComposer(current: Session) {
    if (composer.current.content.trim() || composer.current.title.trim()) await storeComposer(current);
    else { stopEditing(); changeTitle(''); changeContent(''); }
  }

  async function clearSession(current: Session) {
    if (clearing.current) return clearing.current;
    clearing.current = (async () => {
      await keepComposer(current);
      await SecureStore.deleteItemAsync(KEY);
      setSession(null); setProjects([]); setMemories([]); setProposals([]); setSelected(null); setResults(null);
    })();
    try { await clearing.current; } finally { clearing.current = null; }
  }

  async function call<T>(current: Session, path: string, method = 'GET', body?: object): Promise<T> {
    try { return await api<T>(current, path, method, body); }
    catch (e) { if (e instanceof ApiError && e.status === 401) await clearSession(current); throw e; }
  }

  async function load(current: Session) {
    const [nextMemories, nextProposals] = await Promise.all([
      call<Memory[]>(current, '/api/v1/memories?limit=50'),
      call<Proposal[]>(current, '/api/v1/agent/proposals?status=pending&limit=50'),
    ]);
    setMemories(nextMemories); setProposals(nextProposals);
  }

  useEffect(() => {
    (async () => {
      setDrafts(await readDrafts(SecureStore));
      const value = await SecureStore.getItemAsync(KEY);
      if (!value) return;
      const saved = JSON.parse(value) as Session;
      setSession(saved); setServer(saved.origin); setUsername(saved.username);
      api<Project[]>(saved, '/api/v1/projects').then(setProjects).catch(async error => {
        if (error instanceof ApiError && error.status === 401) await clearSession(saved);
      });
    })().catch(error => setError(String(error.message || error))).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (!session) return;
    setMemories([]); setProposals([]); setSelected(null); setResults(null); setDraft(null);
    setScanMessage('');
    load(session).catch(e => setError(String(e.message || e)));
  }, [session?.token, session?.projectId]);

  async function act(task: () => Promise<void>) {
    if (busyNow.current) return;
    busyNow.current = true; setError(''); setBusy(true);
    try { await task(); } catch (e) { setError(String((e as Error).message || e)); }
    finally { busyNow.current = false; setBusy(false); }
  }

  async function signIn() {
    await act(async () => {
      const origin = normalizeOrigin(server);
      const auth = await login(origin, username.trim(), password);
      const provisional: Session = { origin, token: auth.token, username: auth.username, isAdmin: auth.is_admin, projectId: '' };
      const list = await api<Project[]>(provisional, '/api/v1/projects');
      const chosen = list.find(project => project.slug === 'personal') || list[0];
      const next = { ...provisional, projectId: chosen?.id || '', projectName: chosen?.name || 'Personal' };
      await SecureStore.setItemAsync(KEY, JSON.stringify(next));
      setProjects(list); setSession(next); setPassword('');
    });
  }

  async function switchProject(id: string) {
    if (!session) return;
    await act(async () => {
      await keepComposer(session);
      const next = { ...session, projectId: id, projectName: projects.find(project => project.id === id)?.name || '' };
      await SecureStore.setItemAsync(KEY, JSON.stringify(next));
      setSession(next); setTab('Capture'); setCaptureMessage('');
    });
  }

  async function signOut() {
    if (!session) return;
    await act(async () => {
      try { await api(session, '/api/v1/mobile/logout', 'POST'); }
      finally { await clearSession(session); }
    });
  }

  async function deliverDraft(current: Session, item: CaptureDraft) {
    if (item.origin !== current.origin || item.username !== current.username || item.projectId !== current.projectId) {
      throw new Error('Switch to the draft’s original project before sending it.');
    }
    await call(current, '/api/v1/memories', 'POST', { title: item.title, content: item.content, source_type: 'manual' });
    try { await removeDraft(SecureStore, item.id); }
    catch { throw new Error('Sent to Engram, but the local draft could not be removed. Check Memories before sending it again.'); }
    setDrafts(await readDrafts(SecureStore));
    await load(current).catch(() => {});
    if (!projects.length) api<Project[]>(current, '/api/v1/projects').then(setProjects).catch(() => {});
  }

  async function capture() {
    if (!session) return;
    await act(async () => {
      const item = await storeComposer(session);
      try { await deliverDraft(session, item); setCaptureMessage('Saved to Engram.'); }
      catch (error) {
        setCaptureMessage(String((error as Error).message || error).startsWith('Sent to Engram') ? 'Sent to Engram; check Memories before trying again.' : 'Saved securely on this device. Check Memories before retrying if the request timed out.');
        setError(String((error as Error).message || error));
      }
    });
  }

  const card = (item: Memory) => <Pressable key={item.id} style={styles.card} onPress={() => setSelected(item)} accessibilityRole="button">
    <Text style={styles.cardTitle}>{item.title}</Text>
    <Text style={styles.meta}>{item.memory_type} · {new Date(item.updated_at).toLocaleDateString()}</Text>
    <Text style={styles.preview} numberOfLines={2}>{item.content}</Text>
  </Pressable>;

  if (!ready) return <SafeAreaView style={styles.center}><ActivityIndicator color="#7ccaff" /></SafeAreaView>;
  if (!session) return <SafeAreaView style={styles.root}><StatusBar style="light" /><KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <ScrollView contentContainerStyle={styles.login} keyboardShouldPersistTaps="handled">
      <Text style={styles.brand}>ENGRAM</Text><Text style={styles.hero}>Your memory, anywhere.</Text>
      <Text style={styles.sub}>2.7 beta 2 · iOS + Android</Text>
      <Text style={styles.label}>Server URL</Text><TextInput style={styles.input} value={server} onChangeText={setServer} placeholder="https://engram.example.com" placeholderTextColor="#718094" autoCapitalize="none" keyboardType="url" />
      <Text style={styles.label}>Username</Text><TextInput style={styles.input} value={username} onChangeText={setUsername} autoCapitalize="none" placeholder="Username" placeholderTextColor="#718094" />
      <Text style={styles.label}>Password</Text><TextInput style={styles.input} value={password} onChangeText={setPassword} secureTextEntry placeholder="Password" placeholderTextColor="#718094" onSubmitEditing={signIn} />
      {!!error && <Text style={styles.error}>{error}</Text>}
      <Pressable style={styles.primary} onPress={signIn} disabled={busy} accessibilityRole="button"><Text style={styles.primaryText}>{busy ? 'Connecting…' : 'Sign in'}</Text></Pressable>
      <Text style={styles.hint}>Use your Engram account. Your session is stored in your device's secure storage.</Text>
    </ScrollView>
  </KeyboardAvoidingView></SafeAreaView>;

  return <SafeAreaView style={styles.root}><StatusBar style="light" />
    <View style={styles.header}><View><Text style={styles.brandSmall}>ENGRAM</Text><Text style={styles.heading}>{tab}</Text></View><Text style={styles.beta}>BETA 2</Text></View>
    {projects.length > 1 && <ScrollView horizontal style={styles.projectRow} contentContainerStyle={styles.projectContent} showsHorizontalScrollIndicator={false}>
      {projects.map(project => <Pressable key={project.id} style={[styles.chip, session.projectId === project.id && styles.chipActive]} onPress={() => switchProject(project.id)} accessibilityRole="button"><Text style={styles.chipText}>{project.name}</Text></Pressable>)}
    </ScrollView>}
    {!!error && <Text style={styles.errorBanner}>{error}</Text>}
    <ScrollView style={styles.fill} contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
      {tab === 'Capture' && <>
        <Text style={styles.section}>Quick capture</Text>
        <Text style={styles.hint}>Project: {projects.find(project => project.id === session.projectId)?.name || session.projectName || 'Selected project'}</Text>
        {!!editingId && <Text style={styles.hint}>Editing a saved draft</Text>}
        <TextInput style={[styles.input, styles.multiline]} value={content} onChangeText={value => { changeContent(value); setCaptureMessage(''); }} placeholder="What should Engram remember?" placeholderTextColor="#718094" multiline textAlignVertical="top" maxLength={1200} accessibilityLabel="Capture text" />
        <TextInput style={styles.input} value={title} onChangeText={changeTitle} placeholder="Title (optional)" placeholderTextColor="#718094" maxLength={100} accessibilityLabel="Capture title" />
        <Pressable style={styles.primary} disabled={busy || (!content.trim() && !title.trim())} onPress={capture} accessibilityRole="button"><Text style={styles.primaryText}>Save capture</Text></Pressable>
        <Text style={styles.hint}>Saved securely on this device first. Engram sends it now if the server is reachable.</Text>
        {!!captureMessage && <Text style={styles.hint}>{captureMessage}</Text>}
        <Text style={[styles.section, { marginTop: 28 }]}>Saved drafts ({draftsFor(drafts, session).length})</Text>
        {draftsFor(drafts, session).map(item => <View key={item.id} style={styles.card}>
          <Text style={styles.cardTitle}>{item.title}</Text><Text style={styles.preview}>{item.content}</Text>
          <Text style={styles.meta}>{new Date(item.createdAt).toLocaleString()}</Text>
          <View style={styles.row}>
            <Pressable disabled={busy} onPress={() => act(async () => { if (editing.current?.id !== item.id) await keepComposer(session); editing.current = item; setEditingId(item.id); changeTitle(item.title); changeContent(item.content); setCaptureMessage(''); })} accessibilityRole="button"><Text style={styles.link}>Edit</Text></Pressable>
            <Pressable disabled={busy || editingId === item.id} onPress={() => act(async () => { await deliverDraft(session, item); setCaptureMessage('Draft sent to Engram.'); })} accessibilityRole="button"><Text style={styles.link}>Send</Text></Pressable>
            <Pressable disabled={busy} onPress={() => Alert.alert('Delete saved draft?', 'This removes the only local copy.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => { void act(async () => { await removeDraft(SecureStore, item.id); if (editing.current?.id === item.id) { stopEditing(); changeTitle(''); changeContent(''); } setDrafts(await readDrafts(SecureStore)); }); } }])} accessibilityRole="button"><Text style={styles.link}>Delete</Text></Pressable>
          </View>
        </View>)}
        {!draftsFor(drafts, session).length && <Text style={styles.empty}>No drafts waiting to send in this project.</Text>}
      </>}
      {tab === 'Memories' && <>
        {selected ? <><Pressable onPress={() => setSelected(null)}><Text style={styles.link}>← Back to memories</Text></Pressable><Text style={styles.heading}>{selected.title}</Text><Text style={styles.meta}>{selected.memory_type}</Text><Text style={styles.content}>{selected.content}</Text></> :
          <><View style={styles.row}><Text style={styles.section}>{memories.length} recent memories</Text><Pressable onPress={() => setTab('Capture')}><Text style={styles.link}>＋ Capture</Text></Pressable></View>{memories.map(card)}{!memories.length && <Text style={styles.empty}>No memories in this project yet.</Text>}</>}
      </>}
      {tab === 'Search' && <><Text style={styles.section}>Search this project</Text><TextInput style={styles.input} value={query} onChangeText={setQuery} placeholder="What are you looking for?" placeholderTextColor="#718094" returnKeyType="search" onSubmitEditing={() => act(async () => setResults(await call<Memory[]>(session, '/api/v1/search', 'POST', { query: query.trim(), limit: 20, include_documents: false })))} />
        <Pressable style={styles.primary} disabled={busy || !query.trim()} onPress={() => act(async () => setResults(await call<Memory[]>(session, '/api/v1/search', 'POST', { query: query.trim(), limit: 20, include_documents: false })))}><Text style={styles.primaryText}>Search</Text></Pressable>
        {results?.map(card)}{results?.length === 0 && <Text style={styles.empty}>No matches found.</Text>}
        {selected && <View style={styles.card}><Text style={styles.cardTitle}>{selected.title}</Text><Text style={styles.content}>{selected.content}</Text></View>}
      </>}
      {tab === 'Agent' && <><Text style={styles.section}>Memory agent findings</Text><Text style={styles.hint}>Suggestions are for review. The agent never changes memories automatically.</Text>
        <Pressable style={styles.secondary} disabled={busy} onPress={() => act(async () => { setScanMessage(''); const result = await call<{ total: number }>(session, '/api/v1/agent/scan', 'POST'); await load(session); setScanMessage(result.total ? `Scan complete: ${result.total} new finding${result.total === 1 ? '' : 's'}.` : 'Scan complete: no new findings.'); })}><Text style={styles.link}>Run scan</Text></Pressable>
        {!!scanMessage && <Text style={styles.hint}>{scanMessage}</Text>}
        {proposals.map(proposal => <View key={proposal.id} style={styles.card}><Text style={styles.cardTitle}>{proposal.memory_title || proposal.proposal_type.replaceAll('_', ' ')}</Text><Text style={styles.meta}>{proposal.proposal_type}</Text><Text style={styles.preview}>{proposal.reason}</Text>
          <View style={styles.row}>{proposal.proposal_type === 'duplicate' && <Pressable onPress={() => act(async () => { setDraft(await call<Record<string, unknown>>(session, `/api/v1/agent/proposals/${proposal.id}/draft`, 'POST')); })}><Text style={styles.link}>Preview draft</Text></Pressable>}<Pressable onPress={() => act(async () => { await call(session, `/api/v1/agent/proposals/${proposal.id}/dismiss`, 'POST'); await load(session); })}><Text style={styles.link}>Dismiss</Text></Pressable></View>
        </View>)}
        {!proposals.length && <Text style={styles.empty}>No pending findings. Run a scan to check this project.</Text>}
        {draft && <View style={styles.card}><Text style={styles.cardTitle}>Review draft</Text><Text style={styles.preview}>{JSON.stringify(draft, null, 2)}</Text><Text style={styles.hint}>This is a preview only. Review and apply changes in the web app.</Text></View>}
      </>}
      {tab === 'Settings' && <><Text style={styles.section}>Account</Text><Text style={styles.content}>{session.username}</Text><Text style={styles.meta}>{session.origin}</Text><Text style={styles.hint}>Project: {projects.find(p => p.id === session.projectId)?.name || 'Personal'}</Text><Pressable style={styles.secondary} onPress={signOut} disabled={busy}><Text style={styles.link}>Sign out and revoke session</Text></Pressable></>}
    </ScrollView>
    {busy && <ActivityIndicator style={styles.spinner} color="#7ccaff" />}
    <View style={styles.tabBar}>{tabs.map(item => <Pressable key={item} style={[styles.tab, tab === item && styles.tabActive]} onPress={() => { setTab(item); setSelected(null); setError(''); }} accessibilityRole="button"><Text style={[styles.tabText, tab === item && styles.tabTextActive]}>{item}</Text></Pressable>)}</View>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0c1420' }, fill: { flex: 1 }, center: { flex: 1, backgroundColor: '#0c1420', justifyContent: 'center' },
  login: { flexGrow: 1, padding: 28, justifyContent: 'center' }, brand: { color: '#7ccaff', fontSize: 19, fontWeight: '900', letterSpacing: 5 }, brandSmall: { color: '#7ccaff', fontSize: 12, fontWeight: '900', letterSpacing: 3 }, hero: { color: '#f2f7ff', fontSize: 34, fontWeight: '800', marginTop: 22 }, sub: { color: '#96a9bf', marginTop: 8, marginBottom: 34 },
  label: { color: '#b6c9db', fontWeight: '700', marginBottom: 8, marginTop: 16 }, input: { backgroundColor: '#182637', color: '#f2f7ff', borderWidth: 1, borderColor: '#30465c', borderRadius: 14, padding: 15, fontSize: 16, marginBottom: 6 }, multiline: { minHeight: 180 },
  primary: { backgroundColor: '#45aef0', padding: 16, borderRadius: 14, alignItems: 'center', marginTop: 20 }, primaryText: { color: '#071521', fontWeight: '800', fontSize: 16 }, secondary: { padding: 14, borderRadius: 13, borderWidth: 1, borderColor: '#416887', marginTop: 16, alignItems: 'center' },
  hint: { color: '#96a9bf', lineHeight: 20, marginTop: 14 }, error: { color: '#ff9b9b', marginTop: 12 }, errorBanner: { color: '#ffb1b1', backgroundColor: '#532c38', padding: 10 },
  header: { paddingHorizontal: 20, paddingTop: 18, paddingBottom: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }, heading: { color: '#f2f7ff', fontSize: 26, fontWeight: '800', marginTop: 4, marginBottom: 10 }, beta: { color: '#7ccaff', fontSize: 11, fontWeight: '800' },
  projectRow: { flexGrow: 0, maxHeight: 55 }, projectContent: { paddingHorizontal: 20, paddingBottom: 12, gap: 8 }, chip: { paddingHorizontal: 14, paddingVertical: 7, backgroundColor: '#182637', borderRadius: 20 }, chipActive: { backgroundColor: '#22618c' }, chipText: { color: '#f2f7ff', fontWeight: '700' },
  body: { padding: 20, paddingBottom: 40 }, section: { color: '#dbe8f4', fontSize: 18, fontWeight: '800', marginBottom: 14 }, row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 16, marginBottom: 8 }, link: { color: '#7ccaff', fontWeight: '800' },
  card: { backgroundColor: '#172536', borderWidth: 1, borderColor: '#2b4157', borderRadius: 16, padding: 17, marginBottom: 12 }, cardTitle: { color: '#f2f7ff', fontSize: 17, fontWeight: '800', marginBottom: 7 }, meta: { color: '#96a9bf', fontSize: 12, marginBottom: 7 }, preview: { color: '#c5d6e6', lineHeight: 21 }, content: { color: '#dce9f5', fontSize: 16, lineHeight: 25, marginVertical: 14 }, empty: { color: '#96a9bf', marginTop: 28, textAlign: 'center' },
  tabBar: { borderTopWidth: 1, borderTopColor: '#2b4157', flexDirection: 'row', paddingBottom: 8, backgroundColor: '#0d1928' }, tab: { flex: 1, paddingVertical: 14, alignItems: 'center' }, tabActive: { borderTopWidth: 2, borderTopColor: '#7ccaff' }, tabText: { color: '#8ba1b7', fontSize: 12, fontWeight: '700' }, tabTextActive: { color: '#7ccaff' }, spinner: { position: 'absolute', right: 18, bottom: 78 },
});
