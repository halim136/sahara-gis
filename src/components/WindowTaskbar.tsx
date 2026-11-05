import React, { useSyncExternalStore } from 'react';
import { subscribeWindows, getMinimized } from './windowManager';

/** A bottom taskbar of buttons for minimized windows; click one to restore it. Mounted once. */
export const WindowTaskbar: React.FC<{ lang?: 'ar' | 'en' }> = ({ lang }) => {
  const entries = useSyncExternalStore(subscribeWindows, getMinimized);
  if (entries.length === 0) return null;
  return (
    <div
      className="fixed bottom-7 inset-x-0 z-[2000] flex flex-wrap items-center justify-center gap-1.5 px-2 pointer-events-none"
      aria-label={lang === 'en' ? 'Minimized windows' : 'النوافذ المصغّرة'}
    >
      {entries.map((e) => (
        <button
          key={e.id}
          onClick={e.restore}
          className="pointer-events-auto max-w-[220px] truncate flex items-center gap-1.5 px-3 py-1.5 rounded-t-md bg-slate-800 hover:bg-slate-700 text-slate-100 text-xs border border-slate-600 border-b-0 shadow-lg"
          title={e.title}
        >
          <span className="w-2 h-2 rounded-full bg-sky-400 shrink-0" />
          <span className="truncate">{e.title}</span>
        </button>
      ))}
    </div>
  );
};
