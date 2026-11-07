import React, { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { Minus, Square, Copy } from 'lucide-react';
import { addMinimized, removeMinimized } from './windowManager';
import { storeAppValue } from '../utils/portableState';

const WIN_KEY = 'sas:windows:v1';
function readWins(): Record<string, any> {
  try { return JSON.parse(localStorage.getItem(WIN_KEY) || '{}') || {}; } catch { return {}; }
}

interface DraggableWindowProps {
  children: React.ReactElement<any>;
  lang?: 'ar' | 'en';
  onKeyDown?: (e: React.KeyboardEvent) => void;
}

interface Geom { left: number; top: number; width: number; height: number }

let zTop = 1200;

/**
 * A full floating window: drag by the title bar, resize from any edge/corner,
 * maximize/restore, and minimize to the bottom taskbar. Self-positioned (fixed),
 * so the map stays usable behind it. Expects one child: the panel whose first
 * element is its title bar.
 */
export const DraggableWindow: React.FC<DraggableWindowProps> = ({ children, lang, onKeyDown }) => {
  const ar = lang !== 'en';
  const id = useId();
  const winRef = useRef<HTMLDivElement | null>(null);
  const childRef = useRef<HTMLElement | null>(null);
  const [geom, setGeom] = useState<Geom | null>(null);
  const [minimized, setMinimized] = useState(false);
  const [maximized, setMaximized] = useState(false);
  const [z, setZ] = useState(() => ++zTop);
  const prevGeom = useRef<Geom | null>(null);
  const titleRef = useRef('');
  const mode = useRef<{ kind: 'drag' | 'resize'; dir?: string; sx: number; sy: number; g: Geom } | null>(null);

  const onScreen = (g: Geom) => g && g.width >= 240 && g.height >= 120 &&
    g.left < window.innerWidth - 60 && g.left + g.width > 60 && g.top >= 0 && g.top < window.innerHeight - 40;

  // Measure the naturally-sized window once; restore a saved size/position if any.
  useLayoutEffect(() => {
    const el = winRef.current;
    if (!el || geom) return;
    const r = el.getBoundingClientRect();
    const header = childRef.current?.firstElementChild as HTMLElement | null;
    titleRef.current = (header?.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40) || (ar ? 'نافذة' : 'Window');
    const saved = readWins()[titleRef.current] as Geom | undefined;
    if (saved && onScreen(saved)) { setGeom(saved); return; }
    const width = Math.min(r.width, window.innerWidth - 16);
    const height = Math.min(r.height, window.innerHeight * 0.86);
    setGeom({ left: Math.max(8, (window.innerWidth - width) / 2), top: Math.max(8, r.top), width, height });
  }, []);

  // Persist the normal (non-maximized) size/position per window title (disk-synced in the portable app).
  useEffect(() => {
    if (!geom || !titleRef.current) return;
    const g = maximized && prevGeom.current ? prevGeom.current : geom;
    const all = readWins();
    all[titleRef.current] = g;
    try { storeAppValue(WIN_KEY, JSON.stringify(all)); } catch {}
  }, [geom, maximized]);

  useEffect(() => () => removeMinimized(id), [id]);

  const bringFront = () => setZ(++zTop);

  const headerRect = () => (childRef.current?.firstElementChild as HTMLElement | null)?.getBoundingClientRect();

  const onPointerDown = (e: React.PointerEvent) => {
    bringFront();
    if (maximized || !geom) return;
    const target = e.target as HTMLElement;
    if (target.closest('.sas-win-ctrl, .sas-win-resize')) return; // controls/handles handle themselves
    if (target.closest('button,input,select,textarea,a,label,[role="separator"],[contenteditable="true"]')) return;
    const hr = headerRect();
    if (!hr || e.clientY > hr.bottom) return; // only drag from the title bar
    mode.current = { kind: 'drag', sx: e.clientX, sy: e.clientY, g: geom };
    try { winRef.current?.setPointerCapture(e.pointerId); } catch {}
  };

  const startResize = (dir: string) => (e: React.PointerEvent) => {
    if (maximized || !geom) return;
    e.stopPropagation();
    bringFront();
    mode.current = { kind: 'resize', dir, sx: e.clientX, sy: e.clientY, g: geom };
    try { winRef.current?.setPointerCapture(e.pointerId); } catch {}
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const m = mode.current;
    if (!m) return;
    const dx = e.clientX - m.sx, dy = e.clientY - m.sy;
    if (m.kind === 'drag') {
      let left = m.g.left + dx, top = m.g.top + dy;
      left = Math.min(window.innerWidth - 90, Math.max(90 - m.g.width, left));
      top = Math.min(window.innerHeight - 44, Math.max(0, top));
      setGeom({ ...m.g, left, top });
    } else {
      const MIN_W = 300, MIN_H = 140, d = m.dir || '';
      let { left, top, width, height } = m.g;
      if (d.includes('e')) width = Math.max(MIN_W, m.g.width + dx);
      if (d.includes('s')) height = Math.max(MIN_H, m.g.height + dy);
      if (d.includes('w')) { width = Math.max(MIN_W, m.g.width - dx); left = m.g.left + (m.g.width - width); }
      if (d.includes('n')) { height = Math.max(MIN_H, m.g.height - dy); top = m.g.top + (m.g.height - height); }
      setGeom({ left, top, width, height });
    }
  };
  const endPointer = () => { mode.current = null; };

  const toggleMax = () => {
    if (!geom) return;
    if (maximized) { if (prevGeom.current) setGeom(prevGeom.current); setMaximized(false); }
    else {
      prevGeom.current = geom;
      const top = (document.querySelector('.desktop-header') as HTMLElement | null)?.getBoundingClientRect().bottom || 0;
      setGeom({ left: 4, top: top + 4, width: window.innerWidth - 8, height: window.innerHeight - top - 12 });
      setMaximized(true);
    }
    bringFront();
  };

  const doMinimize = () => {
    setMinimized(true);
    addMinimized({ id, title: titleRef.current, restore: () => { setMinimized(false); setZ(++zTop); removeMinimized(id); } });
  };

  const winStyle: React.CSSProperties = geom
    ? { position: 'fixed', left: geom.left, top: geom.top, width: geom.width, height: geom.height, zIndex: z, display: minimized ? 'none' : 'flex', flexDirection: 'column', pointerEvents: 'auto', overflow: 'hidden' }
    : { position: 'fixed', left: '50%', top: '7vh', transform: 'translateX(-50%)', maxHeight: '86vh', zIndex: z, display: 'flex', flexDirection: 'column', visibility: 'hidden', pointerEvents: 'auto' };

  const prevStyle = (children.props.style || {}) as React.CSSProperties;
  const panel = React.cloneElement(children, {
    ref: (el: HTMLElement | null) => {
      childRef.current = el;
      const r: any = (children as any).ref;
      if (typeof r === 'function') r(el); else if (r && typeof r === 'object') r.current = el;
    },
    style: {
      ...prevStyle,
      position: 'relative', margin: 0, inset: 'auto', transform: 'none',
      // Neutralize any CSS z-index on the panel (docked asides use z-index:450)
      // so the resize handles and controls sit above it and stay clickable.
      zIndex: 0,
      width: '100%', height: 'auto', maxWidth: 'none', maxHeight: 'none',
      flex: '1 1 auto', minHeight: 0
    }
  } as any);

  const ctrlStyle: React.CSSProperties = {
    width: 26, height: 24, display: 'flex', alignItems: 'center', justifyContent: 'center',
    borderRadius: 4, background: 'rgba(30,41,59,0.92)', color: '#e2e8f0',
    border: '1px solid rgba(71,85,105,0.7)', cursor: 'pointer'
  };
  const handle = (dir: string, style: React.CSSProperties) => (
    <div className="sas-win-resize" onPointerDown={startResize(dir)} style={{ position: 'absolute', zIndex: 5, touchAction: 'none', ...style }} />
  );
  const E = 9; // edge grab thickness

  return (
    <div
      ref={winRef}
      className="sas-window"
      style={winStyle}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPointer}
      onPointerCancel={endPointer}
      onKeyDown={onKeyDown}
    >
      {panel}

      {/* Window controls (minimize / maximize) beside the panel's own close button */}
      <div className="sas-win-ctrl" style={{ position: 'absolute', top: 6, [ar ? 'left' : 'right']: 44, zIndex: 10, display: 'flex', gap: 4 }}>
        <button type="button" onClick={doMinimize} title={ar ? 'تصغير' : 'Minimize'} aria-label={ar ? 'تصغير' : 'Minimize'} style={ctrlStyle}><Minus size={14} /></button>
        <button type="button" onClick={toggleMax} title={maximized ? (ar ? 'استعادة' : 'Restore') : (ar ? 'تكبير' : 'Maximize')} aria-label={maximized ? (ar ? 'استعادة' : 'Restore') : (ar ? 'تكبير' : 'Maximize')} style={ctrlStyle}>{maximized ? <Copy size={12} /> : <Square size={11} />}</button>
      </div>

      {/* Resize handles (hidden while maximized) */}
      {!maximized && geom && (
        <>
          {handle('n', { top: 0, left: E, right: E, height: E, cursor: 'ns-resize' })}
          {handle('s', { bottom: 0, left: E, right: E, height: E, cursor: 'ns-resize' })}
          {handle('e', { top: E, bottom: E, right: 0, width: E, cursor: 'ew-resize' })}
          {handle('w', { top: E, bottom: E, left: 0, width: E, cursor: 'ew-resize' })}
          {handle('ne', { top: 0, right: 0, width: 14, height: 14, cursor: 'nesw-resize' })}
          {handle('nw', { top: 0, left: 0, width: 14, height: 14, cursor: 'nwse-resize' })}
          {handle('se', { bottom: 0, right: 0, width: 14, height: 14, cursor: 'nwse-resize' })}
          {handle('sw', { bottom: 0, left: 0, width: 14, height: 14, cursor: 'nesw-resize' })}
        </>
      )}
    </div>
  );
};
