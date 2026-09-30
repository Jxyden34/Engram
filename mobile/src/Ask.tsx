import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import type { AskAnswer, Memory } from './api';

type Props = {
  projectId: string;
  projectName: string;
  request: <T>(path: string, method?: string, body?: object) => Promise<T>;
  onOpen: (memory: Memory) => void;
  onCapture: (title: string, content: string) => Promise<void>;
  disabled: boolean;
};

export default function Ask({ projectId, projectName, request, onOpen, onCapture, disabled }: Props) {
  const [question, setQuestion] = useState('');
  const [answers, setAnswers] = useState<AskAnswer[]>([]);
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

  const ask = () => act(async () => {
    if (!question.trim()) return;
    const answer = await request<AskAnswer>('/api/v1/ask', 'POST', { question: question.trim() });
    if (answer.project_id !== projectId) throw new Error('The answer belongs to another project. Please try again.');
    if (mounted.current) { setAnswers(previous => [answer, ...previous].slice(0, 5)); setQuestion(''); }
  });

  return <>
    <Text style={styles.heading}>Ask your memories</Text>
    <Text style={styles.hint}>Ask about {projectName}. Answers use this project’s memories and show the supporting excerpts. Check the sources before relying on an answer.</Text>
    <TextInput style={styles.input} value={question} onChangeText={setQuestion} maxLength={1000} multiline placeholder="What did we decide about the launch?" placeholderTextColor="#718094" accessibilityLabel="Ask Engram question" />
    <View style={styles.suggestions}>{['What decisions have we made?', 'What are the next actions?'].map(example => <Pressable key={example} disabled={busy || disabled} accessibilityRole="button" onPress={() => setQuestion(example)}><Text style={styles.link}>{example}</Text></Pressable>)}</View>
    <Pressable style={styles.button} disabled={busy || disabled || !question.trim()} accessibilityRole="button" onPress={ask}><Text style={styles.link}>{busy ? 'Checking project memories…' : 'Ask Engram'}</Text></Pressable>
    {busy && <ActivityIndicator style={{ marginTop: 16 }} color="#7ccaff" />}
    {!!error && <Text style={styles.error}>{error}</Text>}
    {answers.map((answer, index) => <View key={index} style={styles.card}>
      <Text style={styles.heading}>{answer.question}</Text>
      {answer.insufficient && <Text style={styles.content}>I couldn’t find enough information in this project’s memories to answer that.</Text>}
      {answer.claims.map((claim, i) => {
        const source = answer.sources.find(item => item.number === claim.source);
        return <View key={i} style={{ marginBottom: 20 }}><Text style={styles.content}>{claim.text} [{claim.source}]</Text><Text style={styles.quote}>“{claim.quote}”</Text>{source && <Pressable disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
          const memory = await request<Memory>(`/api/v1/memories/${source.id}`);
          if (mounted.current) onOpen(memory);
        })}><Text style={styles.link}>[{claim.source}] {source.title} →</Text></Pressable>}</View>;
      })}
      {answer.insufficient && answer.sources.map(source => <Pressable key={source.id} style={{ marginTop: 14 }} disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
        const memory = await request<Memory>(`/api/v1/memories/${source.id}`);
        if (mounted.current) onOpen(memory);
      })}><Text style={styles.link}>Read: {source.title} →</Text></Pressable>)}
      {!!answer.claims.length && <Pressable style={styles.button} disabled={busy || disabled} accessibilityRole="button" onPress={() => act(async () => {
        await onCapture(`Answer: ${answer.question}`.slice(0, 100), answer.claims.map(claim => `${claim.text}\nSource: ${answer.sources.find(item => item.number === claim.source)?.title || claim.source}`).join('\n\n'));
      })}><Text style={styles.link}>Review answer as new capture</Text></Pressable>}
    </View>)}
  </>;
}

const styles = StyleSheet.create({
  heading: { color: '#f2f7ff', fontSize: 20, fontWeight: '800', marginBottom: 12 },
  hint: { color: '#96a9bf', lineHeight: 20, marginBottom: 18 },
  input: { backgroundColor: '#182637', color: '#f2f7ff', borderWidth: 1, borderColor: '#30465c', borderRadius: 14, padding: 15, fontSize: 16, minHeight: 110 },
  suggestions: { gap: 14, marginVertical: 18 },
  button: { padding: 14, borderRadius: 13, borderWidth: 1, borderColor: '#416887', marginTop: 12, alignItems: 'center' },
  link: { color: '#7ccaff', fontWeight: '800' },
  content: { color: '#dce9f5', fontSize: 16, lineHeight: 25, marginVertical: 12 },
  quote: { color: '#96a9bf', lineHeight: 22, borderLeftWidth: 2, borderLeftColor: '#7ccaff', paddingLeft: 12, marginBottom: 12 },
  error: { color: '#ff9b9b', marginVertical: 12 },
  card: { backgroundColor: '#172536', borderWidth: 1, borderColor: '#2b4157', borderRadius: 16, padding: 17, marginTop: 24 },
});
