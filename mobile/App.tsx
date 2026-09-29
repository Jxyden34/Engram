import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SecureStore from 'expo-secure-store';
import { api, AgentDraft, ApiError, login, Memory, normalizeOrigin, Project, Proposal, ScanRun, Session } from './src/api';
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
  const [runs, setRuns] = useState<ScanRun[]>([]);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [reviewSources, setReviewSources] = useState<Memory[]>([]);
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
  const [draft, setDraft] = useState<AgentDraft | null>(null);
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
      setSession(null); setProjects([]); setMemories([]); setProposals([]); setRuns([]); setReviewId(null); setReviewSources([]); setSelected(null); setResults(null);
    })();
    try { await clearing.current; } finally { clearing.current = null; }
  }

  async function call<T>(current: Session, path: string, method = 'GET', body?: object): Promise<T> {
    try { return await api<T>(current, path, method, body); }
    catch (e) { if (e instanceof ApiError && e.status === 401) await clearSession(current); throw e; }
  }

  async function load(current: Session) {
    const [nextMemories, nextProposals, nextRuns] = await Promise.all([
      call<Memory[]>(current, '/api/v1/memories?limit=50'),
      call<Proposal[]>(current, '/api/v1/agent/proposals?status=pending&limit=50'),
      call<ScanRun[]>(current, '/api/v1/agent/runs?limit=5'),
    ]);
    setMemories(nextMemories); setProposals(nextProposals); setRuns(nextRuns);
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
    setMemories([]); setProposals([]); setRuns([]); setReviewId(null); setReviewSources([]); setSelected(null); setResults(null); setDraft(null);
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

  async function openReview(proposal: Proposal) {
    if (!session) return;
    await act(async () => {
      const ids = [proposal.memory_id, proposal.related_memory_id].filter((id): id is string => !!id);
      const sources = await Promise.all(ids.map(id => call<Memory>(session, `/api/v1/memories/${id}`)));
      setReviewSources(sources); setReviewId(proposal.id); setDraft(proposal.evidence?.draft || null);
    });
  }

  async function useAgentDraft(proposal: Proposal, suggestion: AgentDraft) {
    if (!session || !suggestion.safe_to_merge || !suggestion.title || !suggestion.content || proposal.draft_stale) return;
    await act(async () => {
      await keepComposer(session);
      changeTitle(suggestion.title || ''); changeContent(suggestion.content || '');
      setTab('Capture'); setCaptureMessage('Review this draft before saving it as a new memory. The source memories stay unchanged.');
    });
  }

  function confirmDismiss(proposal: Proposal) {
    if (!session) return;
    Alert.alert('Dismiss finding?', 'This removes the finding from the pending review list. It does not change either memory.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Dismiss', style: 'destructive', onPress: () => { void act(async () => {
        await call(session, `/api/v1/agent/proposals/${proposal.id}/dismiss`, 'POST');
        setReviewId(null); setReviewSources([]); setDraft(null); await load(session);
      }); } },
    ]);
  }

  const review = proposals.find(item => item.id === reviewId);
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
    <ScrollView horizontal style={styles.tabBar} contentContainerStyle={styles.tabContent} showsHorizontalScrollIndicator={false}>
      {tabs.map(item => <Pressable key={item} style={[styles.tab, tab === item && styles.tabActive]} onPress={() => { setTab(item); setSelected(null); setError(''); }} accessibilityRole="button"><Text style={[styles.tabText, tab === item && styles.tabTextActive]}>{item}</Text></Pressable>)}
    </ScrollView>
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
      {tab === 'Agent' && <><Text style={styles.section}>Memory agent findings</Text><Text style={styles.hint}>Review source memories before using a suggestion. The agent never changes them automatically.</Text>
        <Pressable style={styles.secondary} disabled={busy} onPress={() => act(async () => { setScanMessage(''); const result = await call<{ total: number }>(session, '/api/v1/agent/scan', 'POST'); await load(session); setScanMessage(result.total ? `Scan complete: ${result.total} new finding${result.total === 1 ? '' : 's'}.` : 'Scan complete: no new findings.'); })}><Text style={styles.link}>Run scan</Text></Pressable>
        {!!scanMessage && <Text style={styles.hint}>{scanMessage}</Text>}
        {review ? <>
          <Pressable onPress={() => { setReviewId(null); setReviewSources([]); setDraft(null); }} accessibilityRole="button"><Text style={styles.link}>← Back to findings</Text></Pressable>
          <Text style={[styles.section, { marginTop: 20 }]}>{review.proposal_type.replaceAll('_', ' ')} review</Text>
          <Text style={styles.preview}>{review.reason}</Text>
          {Object.entries(review.evidence || {}).filter(([key]) => key !== 'draft').map(([key, value]) => <Text key={key} style={styles.meta}>{key.replaceAll('_', ' ')}: {String(value)}</Text>)}
          <Text style={[styles.section, { marginTop: 24 }]}>Source memories</Text>
          {reviewSources.map(source => <View key={source.id} style={styles.card}><Text style={styles.cardTitle}>{source.title}</Text><Text style={styles.content}>{source.content}</Text><Text style={styles.meta}>Updated {new Date(source.updated_at).toLocaleString()}</Text></View>)}
          {review.proposal_type === 'duplicate' && <Pressable style={styles.secondary} disabled={busy} onPress={() => act(async () => { const result = await call<AgentDraft>(session, `/api/v1/agent/proposals/${review.id}/draft`, 'POST'); setDraft(result); await load(session); })} accessibilityRole="button"><Text style={styles.link}>{draft ? 'Regenerate draft' : 'Generate consolidation draft'}</Text></Pressable>}
          {draft && <View style={[styles.card, { marginTop: 16 }]}><Text style={styles.cardTitle}>{draft.safe_to_merge ? draft.title : 'Keep these separate'}</Text><Text style={styles.preview}>{draft.reason}</Text>{!!draft.content && <Text style={styles.content}>{draft.content}</Text>}
            {review.draft_stale && <Text style={styles.error}>A source changed since this draft. Regenerate it before use.</Text>}
            {draft.safe_to_merge && !review.draft_stale && !!draft.title && !!draft.content && <Pressable style={styles.secondary} disabled={busy} onPress={() => useAgentDraft(review, draft)} accessibilityRole="button"><Text style={styles.link}>Use as new capture</Text></Pressable>}
          </View>}
          <Pressable style={styles.secondary} disabled={busy} onPress={() => confirmDismiss(review)} accessibilityRole="button"><Text style={styles.link}>Dismiss finding</Text></Pressable>
        </> : <>
          <Text style={[styles.section, { marginTop: 24 }]}>{proposals.length} pending</Text>
          {proposals.map(proposal => <View key={proposal.id} style={styles.card}><Text style={styles.cardTitle}>{proposal.memory_title || proposal.proposal_type.replaceAll('_', ' ')}</Text><Text style={styles.meta}>{proposal.proposal_type.replaceAll('_', ' ')}{proposal.related_title ? ` · ${proposal.related_title}` : ''}</Text><Text style={styles.preview}>{proposal.reason}</Text><Pressable style={styles.secondary} disabled={busy} onPress={() => openReview(proposal)} accessibilityRole="button"><Text style={styles.link}>Review sources and actions</Text></Pressable></View>)}
        </>}
        {!proposals.length && <Text style={styles.empty}>No pending findings. Run a scan to check this project.</Text>}
        <Text style={[styles.section, { marginTop: 28 }]}>Recent scans</Text>
        {runs.map(run => <View key={run.id} style={styles.card}><Text style={styles.cardTitle}>{run.trigger_type === 'scheduled' ? 'Automatic' : 'Manual'} scan · {run.status}</Text><Text style={styles.meta}>{new Date(run.created_at).toLocaleString()}</Text>{run.result && <Text style={styles.preview}>{run.result.total} new findings</Text>}{!!run.error_message && <Text style={styles.error}>{run.error_message}</Text>}</View>)}
        {!runs.length && <Text style={styles.empty}>No scans yet.</Text>}
      </>}
      {tab === 'Settings' && <><Text style={styles.section}>Account</Text><Text style={styles.content}>{session.username}</Text><Text style={styles.meta}>{session.origin}</Text><Text style={styles.hint}>Project: {projects.find(p => p.id === session.projectId)?.name || 'Personal'}</Text><Pressable style={styles.secondary} onPress={signOut} disabled={busy}><Text style={styles.link}>Sign out and revoke session</Text></Pressable></>}
    </ScrollView>
    {busy && <ActivityIndicator style={styles.spinner} color="#7ccaff" />}
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
  tabBar: { flexGrow: 0, borderBottomWidth: 1, borderBottomColor: '#2b4157', backgroundColor: '#0d1928' }, tabContent: { paddingHorizontal: 12, gap: 4 }, tab: { minWidth: 76, paddingHorizontal: 12, paddingVertical: 14, alignItems: 'center' }, tabActive: { borderBottomWidth: 2, borderBottomColor: '#7ccaff' }, tabText: { color: '#8ba1b7', fontSize: 12, fontWeight: '700' }, tabTextActive: { color: '#7ccaff' }, spinner: { position: 'absolute', right: 18, bottom: 24 },
});
