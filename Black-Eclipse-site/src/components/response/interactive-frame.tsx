'use client';

// ── InteractiveFrame — the sandbox host ──────────────────────────────────────
//
// Mounts the composed document in an iframe with `sandbox="allow-scripts"` and
// NO `allow-same-origin`: the frame runs in an opaque origin, so it cannot read
// this page's DOM, cookies or storage, and its CSP blocks all network access.
//
// The only channel is postMessage. Every message is checked against the frame's
// contentWindow and the per-render nonce. The host pushes the dataset snapshot
// and the host context (theme/locale/motion); the frame may only ask for a
// resize or report an error.

import { useCallback, useEffect, useRef } from 'react';
import type { InteractiveContext } from '@/lib/interactive/document';
import type { InteractiveDatasetEnvelope } from '@/lib/interactive/dataset';

export interface InteractiveFrameProps {
  srcDoc: string;
  title: string;
  /** A pixel height inline, or `100%` when the host fills the viewport. */
  height: number | string;
  nonce: string;
  envelope: InteractiveDatasetEnvelope;
  context: InteractiveContext;
  /** False when the card is scrolled out of view or the tab is hidden. */
  onScreen: boolean;
  /** Fade the frame in once the app has signalled ready. */
  visible?: boolean;
  onResize: (height: number) => void;
  onReady?: () => void;
  onError?: (message: string) => void;
}

interface FrameMessage {
  type?: unknown;
  nonce?: unknown;
  height?: unknown;
  message?: unknown;
}

export function InteractiveFrame({
  srcDoc,
  title,
  height,
  nonce,
  envelope,
  context,
  onScreen,
  visible = true,
  onResize,
  onReady,
  onError,
}: InteractiveFrameProps) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const readyRef = useRef(false);
  const envelopeRef = useRef(envelope);
  const contextRef = useRef(context);
  envelopeRef.current = envelope;
  contextRef.current = context;

  const sendState = useCallback(() => {
    const frame = frameRef.current;
    if (!frame?.contentWindow || !readyRef.current) return;
    frame.contentWindow.postMessage(
      { type: 'eclipse:data', nonce, envelope: envelopeRef.current },
      '*',
    );
    frame.contentWindow.postMessage(
      { type: 'eclipse:context', nonce, context: contextRef.current },
      '*',
    );
    frame.contentWindow.postMessage(
      { type: 'eclipse:visibility', nonce, visible: onScreen },
      '*',
    );
  }, [nonce, onScreen]);

  useEffect(() => {
    readyRef.current = false;
  }, [srcDoc, nonce]);

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      const frame = frameRef.current;
      if (!frame || event.source !== frame.contentWindow) return;
      const message = event.data as FrameMessage | null;
      if (!message || message.nonce !== nonce) return;

      if (message.type === 'eclipse:ready') {
        readyRef.current = true;
        sendState();
        onReady?.();
        return;
      }
      if (message.type === 'eclipse:resize' && typeof message.height === 'number' && Number.isFinite(message.height)) {
        onResize(Math.max(240, Math.min(900, Math.round(message.height))));
        return;
      }
      if (message.type === 'eclipse:error' && typeof message.message === 'string') {
        onError?.(message.message.slice(0, 400));
      }
    }

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [nonce, onResize, onReady, onError, sendState]);

  useEffect(() => {
    sendState();
  }, [envelope, context, onScreen, sendState]);

  return (
    <iframe
      ref={frameRef}
      title={title}
      srcDoc={srcDoc}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      loading="lazy"
      className="block w-full border-0 bg-transparent"
      style={{
        height,
        opacity: visible ? 1 : 0,
        transition: 'opacity 180ms ease',
      }}
    />
  );
}
