export function appendTranscript(content: string, transcript: string): string {
  const spoken = transcript.trim();
  if (!spoken) throw new Error('No speech captured. Try again or type your memory.');
  const result = [content.trimEnd(), spoken].filter(Boolean).join('\n');
  if (result.length > 1200) throw new Error('The combined capture is too long. Edit the transcript before adding it.');
  return result;
}
