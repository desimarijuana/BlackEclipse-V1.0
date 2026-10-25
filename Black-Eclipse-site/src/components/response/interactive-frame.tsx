'use client';

// ── InteractiveFrame — the sandbox host ──────────────────────────────────────
//
// Mounts the composed document in an iframe with `sandbox="allow-scripts"` and
// NO `allow-same-origin`: the frame runs in an opaque origin, so it cannot read
// this page's DOM, cookies or storage, and its CSP blocks all network access.
//
// The only channel is postMessage. Every message is checked against the frame's
// contentWindow and the per-render nonce. The host pushes the dataset snapshot;
// the frame may only ask for a resize.

import { useCallback, useEffect, useRef } from 'react';
import type { InteractiveDatasetEnvelope } from '@/lib/interactive/dataset';

export interface InteractiveFrameProps {
  srcDoc: string;
  title: string;
  height: number;
  nonce: string;
  envelope: InteractiveDatasetEnvelope;
  onResize: (height: number) => void;
}

interface FrameMessage {
  type?: unknown;
  nonce?: unknown;
  height?: unknown;
}

export function InteractiveFrame({ srcDoc, title, height, nonce, envelope, onResize }: InteractiveFrameProps) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const readyRef = useRef(false);
  const envelopeRef = useRef(envelope);
  envelopeRef.current = envelope;

  const sendEnvelope = useCallback(() => {
    const frame = frameRef.current;
    if (!frame?.contentWindow || !readyRef.current) return;
    frame.contentWindow.postMessage(
      { type: 'eclipse:data', nonce, envelope: envelopeRef.current },
      '*',
    );
  }, [nonce]);

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
        sendEnvelope();
        return;
      }
      if (message.type === 'eclipse:resize' && typeof message.height === 'number' && Number.isFinite(message.height)) {
        onResize(Math.max(240, Math.min(900, Math.round(message.height))));
      }
    }

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [nonce, onResize, sendEnvelope]);

  useEffect(() => {
    sendEnvelope();
  }, [envelope, sendEnvelope]);

  return (
    <iframe
      ref={frameRef}
      title={title}
      srcDoc={srcDoc}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      loading="lazy"
      className="block w-full border-0 bg-transparent"
      style={{ height }}
    />
  );
}
