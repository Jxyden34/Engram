import { useEffect, useState } from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors } from './theme';

type Notice = { id: string; title: string; detail: string; href: string; severity: string; read_at?: string; created_at: string };
type Result = { items: Notice[]; unread: number };
type Props = { origin: string; request: <T>(path: string, method?: string) => Promise<T> };

export default function Notifications({ origin, request }: Props) {
  const [data, setData] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function load() {
    try { setData(await request<Result>('/api/v1/notifications')); }
    catch (e) { setError((e as Error).message); }
  }
  useEffect(() => { void load(); }, []);
  async function act(path: string) {
    setBusy(true); setError('');
    try { await request(path, 'POST'); await load(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <View>
    <Text style={styles.heading}>{data ? data.unread + ' unread' : 'Notifications'}</Text>
    <Pressable accessibilityRole="button" disabled={busy} style={styles.button} onPress={() => void act('/api/v1/notifications/refresh')}>
      <Text style={styles.link}>{busy ? 'Updating…' : 'Check now'}</Text>
    </Pressable>
    {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    {data?.items.length === 0 && <Text style={styles.meta}>No active notifications in this project.</Text>}
    {data?.items.map(item => <View key={item.id} style={styles.card}>
      <Text style={styles.meta}>{item.severity} · {item.read_at ? 'Read' : 'Unread'}</Text>
      <Text style={styles.heading}>{item.title}</Text>
      <Text style={styles.body}>{item.detail}</Text>
      <Pressable style={styles.button} accessibilityRole="link" onPress={() => {
        // Only link to routes on the configured server.
        if (item.href.startsWith('/') && !item.href.startsWith('//') && !item.href.includes('\\')) {
          void Linking.openURL(origin + item.href).catch(() => setError('Could not open the source.'));
        }
      }}><Text style={styles.link}>Review source in browser</Text></Pressable>
      {!item.read_at && <Pressable style={styles.button} disabled={busy} accessibilityRole="button" onPress={() => void act('/api/v1/notifications/' + item.id + '/read')}><Text style={styles.link}>Mark read</Text></Pressable>}
      <Pressable style={styles.button} disabled={busy} accessibilityRole="button" onPress={() => void act('/api/v1/notifications/' + item.id + '/dismiss')}><Text style={styles.link}>Dismiss</Text></Pressable>
    </View>)}
  </View>;
}
const styles = StyleSheet.create({
  heading: { fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: 10 },
  card: { backgroundColor: colors.panel, borderColor: colors.border, borderWidth: 1, borderRadius: 16, padding: 18, marginTop: 16 },
  body: { color: colors.body, lineHeight: 24 },
  meta: { color: colors.muted, marginVertical: 12 },
  button: { minHeight: 44, padding: 12, marginTop: 8, borderWidth: 1, borderColor: colors.controlBorder, borderRadius: 10 },
  link: { color: colors.accent, fontWeight: '600' },
  error: { color: colors.danger, marginVertical: 12 },
});
