export function modelLabel(id: string): string {
  const parts = id.split('/');
  const run = parts[0].replace(/^server-/, '');
  const seed = parts.find(part => part.startsWith('seed_'))?.replace('seed_', 'S') ?? '';
  const checkpoint = parts.slice(1).filter(part => !part.startsWith('seed_')).join('/');
  return [seed, checkpoint, run].filter(Boolean).join(' · ');
}
