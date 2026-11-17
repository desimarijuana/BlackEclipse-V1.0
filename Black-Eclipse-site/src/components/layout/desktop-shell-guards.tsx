'use client';

// Desktop shell guards
// ---------------------------------------------------------------------------
// Eclipse loads a localhost bundle in the native shell, so without this
// component the WebView keeps its *browser* behaviours: the native context
// menu (Reload / Save as / Print / View source / Inspect), Ctrl+R reload,
// Ctrl+P print, Ctrl+S save-page, Ctrl+plus/minus/0 page zoom, ctrl+wheel
// zoom, and navigating to a file dropped on the window. None of those exist
// in a real application, and each one immediately reads as "a website in a
// window".
//
// Mounted once in the root layout. It deliberately does NOT touch text
// inputs: those keep the platform text menu (undo / cut / copy / paste),
// which a desktop user expects. On app chrome and content a right-click on a
// selection opens a small Eclipse-glass Copy menu instead of the WebView's.
//
// See `.opencode/skills/black-eclipse-ui/SKILL.md` for the glass recipe.

import { useCallback, useEffect, useRef, useState } from 'react';
import { Copy } from '@/lib/icons';
import { isBrowserShortcutKey, isEditableTarget, isFileDrag } from '@/lib/desktop/shell-guards';

interface SelectionMenu {
  x: number;
  y: number;
  text: string;
}

const MENU_WIDTH = 168;
const MENU_HEIGHT = 40;
/** Regions that own their own right-click menu (workspace grid, chart
 *  canvases, custom HUDs). The guard blocks the WebView menu there and lets
 *  the component's own handler render its menu. */
const OWN_CONTEXT_MENU = 'canvas, .workspace-canvas, .graph-canvas, [data-be-context-menu]';

export function DesktopShellGuards() {
  const [menu, setMenu] = useState<SelectionMenu | null>(null);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);
  const menuOpen = useRef(false);

  const closeMenu = useCallback(() => {
    menuOpen.current = false;
    setMenu(null);
    setCopied(false);
  }, []);

  const copy = useCallback(async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // WebView clipboard permission can be denied; the legacy path works
      // from a user gesture and needs no grant.
      const scratch = document.createElement('textarea');
      scratch.value = text;
      scratch.setAttribute('readonly', '');
      scratch.style.position = 'fixed';
      scratch.style.top = '-1000px';
      scratch.style.opacity = '0';
      document.body.appendChild(scratch);
      scratch.select();
      try {
        document.execCommand('copy');
      } catch {
        /* nothing else to try */
      }
      scratch.remove();
    }
    setCopied(true);
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => {
      copyTimer.current = null;
      setCopied(false);
    }, 1200);
  }, []);

  useEffect(() => {
    // Right click: editable fields keep the platform menu. Everywhere else
    // the WebView menu is suppressed; a live text selection gets a themed
    // Copy menu.
    const onContextMenu = (event: MouseEvent) => {
      if (isEditableTarget(event.target)) {
        closeMenu();
        return;
      }
      event.preventDefault();

      const target = event.target as Element | null;
      if (target && typeof target.closest === 'function' && target.closest(OWN_CONTEXT_MENU)) return;

      const selection = window.getSelection();
      const text = selection && !selection.isCollapsed ? selection.toString() : '';
      if (!text.trim()) {
        closeMenu();
        return;
      }
      setCopied(false);
      menuOpen.current = true;
      setMenu({
        x: Math.max(8, Math.min(event.clientX, window.innerWidth - MENU_WIDTH - 8)),
        y: Math.max(8, Math.min(event.clientY, window.innerHeight - MENU_HEIGHT - 8)),
        text,
      });
    };

    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Element | null;
      if (target && typeof target.closest === 'function' && target.closest('[data-be-shell-menu]')) return;
      closeMenu();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && menuOpen.current) {
        closeMenu();
        return;
      }
      // WebView browser chrome (reload / print / save / view-source / zoom).
      if (!isBrowserShortcutKey(event)) return;
      event.preventDefault();
    };

    const onWheel = (event: WheelEvent) => {
      // Ctrl+wheel is the WebView's page-zoom gesture. Chart zoom handlers
      // are untouched: they see the event, it just cannot zoom the app.
      if (event.ctrlKey) event.preventDefault();
    };

    // A file dropped outside a real upload zone would make the WebView
    // navigate to file:// and lose the app. Zones that accept drops call
    // preventDefault themselves, so they are never affected.
    const onDragOver = (event: DragEvent) => {
      if (!event.defaultPrevented && isFileDrag(event)) event.preventDefault();
    };
    const onDrop = (event: DragEvent) => {
      if (!event.defaultPrevented && isFileDrag(event)) event.preventDefault();
    };

    // Links and images must not spawn a browser drag ghost / "drag to new
    // window" affordance. dnd-kit surfaces opt back in with draggable=true.
    const onDragStart = (event: DragEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.closest('[draggable="true"]')) return;
      if (target.closest('a[href]') || target.tagName === 'IMG') event.preventDefault();
    };

    // Middle-click on a link is the browser's "open in a new tab". The shell
    // has one window and its own tab strip, so it must not create one.
    const onAuxClick = (event: MouseEvent) => {
      if (event.button !== 1) return;
      const target = event.target as Element | null;
      if (target && typeof target.closest === 'function' && target.closest('a[href]')) {
        event.preventDefault();
      }
    };

    const onBlur = () => closeMenu();

    document.addEventListener('contextmenu', onContextMenu, true);
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('scroll', closeMenu, true);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('wheel', onWheel, { passive: false });
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('drop', onDrop);
    window.addEventListener('dragstart', onDragStart);
    window.addEventListener('auxclick', onAuxClick);
    window.addEventListener('resize', closeMenu);
    window.addEventListener('blur', onBlur);
    return () => {
      document.removeEventListener('contextmenu', onContextMenu, true);
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('scroll', closeMenu, true);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('wheel', onWheel);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('drop', onDrop);
      window.removeEventListener('dragstart', onDragStart);
      window.removeEventListener('auxclick', onAuxClick);
      window.removeEventListener('resize', closeMenu);
      window.removeEventListener('blur', onBlur);
      if (copyTimer.current) window.clearTimeout(copyTimer.current);
    };
  }, [closeMenu]);

  if (!menu) return null;

  const modKey = typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform) ? 'Cmd+C' : 'Ctrl+C';

  return (
    <div
      data-be-shell-menu
      role="menu"
      aria-label="Selection actions"
      className="glass-card-strong fixed z-[300] min-w-[168px] rounded-lg border border-border/40 p-1"
      style={{ left: menu.x, top: menu.y }}
      onContextMenu={(event) => event.preventDefault()}
    >
      <button
        type="button"
        role="menuitem"
        autoFocus
        onClick={() => void copy(menu.text)}
        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-foreground outline-none transition-colors hover:bg-white/[0.08] focus-visible:bg-white/[0.08]"
      >
        <Copy size={13} className="shrink-0 text-muted-foreground" />
        <span>{copied ? 'Copied' : 'Copy'}</span>
        <span className="ml-auto font-mono text-[10px] text-muted-foreground/60">{modKey}</span>
      </button>
    </div>
  );
}
