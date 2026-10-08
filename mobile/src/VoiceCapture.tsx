import { useEffect, useRef, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { requireOptionalNativeModule } from 'expo';
import type { ExpoSpeechRecognitionModule } from 'expo-speech-recognition';
import { appendTranscript } from './voice';

// Expo Go and older APKs must remain usable without this native module.
const speech = requireOptionalNativeModule<typeof ExpoSpeechRecognitionModule>('ExpoSpeechRecognition');

export default function VoiceCapture({ content, onContent, onKeyboard, disabled }: {
  content: string; onContent: (value: string) => void; onKeyboard: () => void; disabled: boolean;
}) {
  const [listening, setListening] = useState(false);
  const [starting, setStarting] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState('');
  const mounted = useRef(true);
  const working = useRef(false);
  const active = useRef(false);

  useEffect(() => {
    mounted.current = true;
    if (!speech) return () => { mounted.current = false; };
    const listeners = [
      speech.addListener('start', () => { if (mounted.current) setListening(true); }),
      speech.addListener('result', event => { if (mounted.current && active.current) setTranscript(event.results[0]?.transcript || ''); }),
      speech.addListener('end', () => { active.current = false; if (mounted.current) { setListening(false); setStarting(false); } }),
      speech.addListener('error', event => {
        active.current = false;
        if (mounted.current) { setListening(false); setStarting(false); if (event.error !== 'aborted') setError(`Voice capture: ${event.message || event.error}. You can still type or use keyboard dictation.`); }
      }),
    ];
    const background = AppState.addEventListener('change', state => { if (state !== 'active') { active.current = false; speech.abort(); } });
    return () => { mounted.current = false; active.current = false; speech.abort(); listeners.forEach(listener => listener.remove()); background.remove(); };
  }, []);

  async function start() {
    if (!speech || working.current || active.current || disabled) return;
    working.current = true; setStarting(true); setError('');
    try {
      if (!speech.isRecognitionAvailable()) throw new Error('Speech recognition is unavailable on this device');
      const permission = await speech.requestPermissionsAsync();
      if (!mounted.current || AppState.currentState !== 'active') return;
      if (!permission.granted) throw new Error('Microphone or speech permission was denied. Enable it in device Settings');
      active.current = true; setTranscript('');
      speech.start({ lang: 'en-GB', interimResults: true, continuous: false, requiresOnDeviceRecognition: speech.supportsOnDeviceRecognition(), recordingOptions: { persist: false } });
    } catch (e) { if (mounted.current) setError(String((e as Error).message || e)); }
    finally { working.current = false; if (mounted.current) setStarting(false); }
  }

  if (!speech) return <View style={styles.box}>
    <Pressable style={styles.button} disabled={disabled} accessibilityRole="button" onPress={onKeyboard}><Text style={styles.link}>🎙 Voice capture with keyboard</Text></Pressable>
    <Text style={styles.hint}>Tap your keyboard’s microphone, dictate, then review the text before saving. The dedicated voice recorder needs the new Engram build.</Text>
  </View>;

  return <View style={styles.box}>
    <Text style={styles.hint}>Dictate, review, then add the transcript. Engram does not save audio. Your device’s speech service may need a connection when on-device recognition is unavailable.</Text>
    <Pressable style={styles.button} disabled={disabled || starting} accessibilityRole="button" onPress={() => listening ? speech.stop() : void start()}><Text style={styles.link}>{starting ? 'Starting microphone…' : listening ? '■ Stop dictation' : '🎙 Start voice capture'}</Text></Pressable>
    {!!transcript && <>
      <TextInput style={styles.input} value={transcript} onChangeText={setTranscript} editable={!listening && !starting && !disabled} multiline accessibilityLabel="Review voice transcript" />
      <Pressable style={styles.button} disabled={disabled || listening || starting} accessibilityRole="button" onPress={() => {
        try { onContent(appendTranscript(content, transcript)); setTranscript(''); setError(''); }
        catch (e) { setError(String((e as Error).message || e)); }
      }}><Text style={styles.link}>Use reviewed transcript</Text></Pressable>
      <Pressable style={styles.button} disabled={disabled || listening || starting} accessibilityRole="button" onPress={() => { setTranscript(''); setError(''); }}><Text style={styles.link}>Discard transcript</Text></Pressable>
    </>}
    {!!error && <Text style={styles.error}>{error}</Text>}
  </View>;
}

const styles = StyleSheet.create({
  box: { marginVertical: 12 }, button: { borderWidth: 1, borderColor: '#416887', borderRadius: 13, padding: 14, alignItems: 'center', marginTop: 10 },
  link: { color: '#7ccaff', fontWeight: '800' }, hint: { color: '#96a9bf', lineHeight: 20, marginVertical: 8 },
  input: { backgroundColor: '#182637', color: '#f2f7ff', borderRadius: 14, padding: 15, fontSize: 16, minHeight: 100, marginTop: 12 }, error: { color: '#ff9b9b', marginTop: 12 },
});
