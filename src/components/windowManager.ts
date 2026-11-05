// Tiny module-level store for the minimized-window taskbar.
export interface MinimizedEntry { id: string; title: string; restore: () => void }

let entries: MinimizedEntry[] = [];
const listeners = new Set<() => void>();

export function subscribeWindows(l: () => void): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
export function getMinimized(): MinimizedEntry[] { return entries; }

export function addMinimized(e: MinimizedEntry): void {
  entries = [...entries.filter((x) => x.id !== e.id), e];
  listeners.forEach((l) => l());
}
export function removeMinimized(id: string): void {
  if (!entries.some((x) => x.id === id)) return;
  entries = entries.filter((x) => x.id !== id);
  listeners.forEach((l) => l());
}
