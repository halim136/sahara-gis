import React, { useLayoutEffect, useRef, useState } from 'react';

interface DraggableWindowProps {
  children: React.ReactElement<any>;
  lang?: 'ar' | 'en';
  overlayClassName?: string;
  onKeyDown?: (e: React.KeyboardEvent) => void;
}

/**
 * Wraps a modal panel to make it a movable, minimizable window.
 * - Drag the panel by its title bar (the panel's first child) to move it.
 * - A minimize button collapses the window to just its title bar; click again to restore.
 * The overlay itself is click-through so the map stays usable behind the window.
 * It expects exactly one child: the modal's panel <div> (title bar first, then body).
 */
export const DraggableWindow: React.FC<DraggableWindowProps> = ({ children, lang, overlayClassName, onKeyDown }) => {
  const ar = lang !== 'en';
  const panelRef = useRef<HTMLElement | null>(null);
  const [offset, setOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [minimized, setMinimized] = useState(false);
  const drag = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);

  useLayoutEffect(() => {
    const header = panelRef.current?.firstElementChild as HTMLElement | null;
    if (header) header.style.cursor = 'move';
  }, []);

  const headerHeight = () => (panelRef.current?.firstElementChild as HTMLElement | null)?.offsetHeight || 48;

  const onPointerDown = (e: React.PointerEvent) => {
    const panel = panelRef.current;
    if (!panel) return;
    const target = e.target as HTMLElement;
    if (target.closest('button,input,select,textarea,a,label,[role="separator"],[contenteditable="true"]')) return;
    const rect = panel.getBoundingClientRect();
    if (e.clientY - rect.top > headerHeight()) return; // only drag from the title bar
    drag.current = { sx: e.clientX, sy: e.clientY, ox: offset.x, oy: offset.y };
    try { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); } catch {}
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const panel = panelRef.current;
    if (!panel) return;
    let nx = drag.current.ox + (e.clientX - drag.current.sx);
    let ny = drag.current.oy + (e.clientY - drag.current.sy);
    // Keep the title bar reachable on screen.
    const w = panel.offsetWidth, h = panel.offsetHeight;
    const baseLeft = (window.innerWidth - w) / 2;
    const baseTop = (window.innerHeight - h) / 2;
    const left = baseLeft + nx, top = baseTop + ny;
    const clampedLeft = Math.min(window.innerWidth - 90, Math.max(90 - w, left));
    const clampedTop = Math.min(window.innerHeight - 48, Math.max(0, top));
    nx += clampedLeft - left;
    ny += clampedTop - top;
    setOffset({ x: nx, y: ny });
  };

  const endDrag = () => { drag.current = null; };

  const controlStyle: React.CSSProperties = {
    position: 'absolute', top: 7, [ar ? 'left' : 'right']: 48, zIndex: 40,
    width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center',
    borderRadius: 5, background: 'rgba(30,41,59,0.92)', color: '#e2e8f0',
    border: '1px solid rgba(71,85,105,0.7)', fontSize: 15, lineHeight: 1, cursor: 'pointer'
  };

  const minimizeBtn = (
    <button
      key="__sas_min"
      type="button"
      onClick={() => setMinimized((m) => !m)}
      title={minimized ? (ar ? 'استعادة النافذة' : 'Restore window') : (ar ? 'تصغير النافذة' : 'Minimize window')}
      aria-label={minimized ? (ar ? 'استعادة النافذة' : 'Restore window') : (ar ? 'تصغير النافذة' : 'Minimize window')}
      style={controlStyle}
    >{minimized ? '▢' : '—'}</button>
  );

  const prevStyle = (children.props.style || {}) as React.CSSProperties;
  const prevClass = (children.props.className || '') as string;
  const panel = React.cloneElement(children, {
    ref: (el: HTMLElement | null) => {
      panelRef.current = el;
      const r: any = (children as any).ref;
      if (typeof r === 'function') r(el); else if (r && typeof r === 'object') r.current = el;
    },
    onPointerDown,
    onPointerMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
    className: prevClass + ' sas-draggable-window' + (minimized ? ' overflow-hidden' : ''),
    style: {
      ...prevStyle,
      position: 'relative',
      pointerEvents: 'auto',
      transform: `translate(${offset.x}px, ${offset.y}px)`,
      ...(minimized ? { maxHeight: headerHeight(), minHeight: 0 } : {})
    }
  } as any, minimizeBtn, children.props.children);

  return (
    <div
      className={overlayClassName ?? 'fixed inset-0 z-50 flex items-center justify-center p-3'}
      style={{ pointerEvents: 'none' }}
      onKeyDown={onKeyDown}
    >
      {panel}
    </div>
  );
};
