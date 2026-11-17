// Themed replacement for the browser's native `window.confirm/alert/prompt`.
//
// Native dialogs render as OS chrome pinned to the top of the WebView, which
// breaks the Eclipse shell. These helpers queue an in-app frosted-glass dialog
// instead:
//
//   if (!(await confirmDialog({ title: 'Delete this chat?', tone: 'danger' }))) return
//   await alertDialog({ title: 'Export complete', description: path })
//   const name = await promptDialog({ title: 'Rename artifact', defaultValue: old })
//
// This module is deliberately UI-free (no React component imports) so any layer
// — including `src/lib` widgets — can call it. The single
// `<ConfirmDialogHost />` in the root layout subscribes to the queue and renders
// the dialog through the glass system.

import type { ReactNode } from "react"

export type ConfirmTone = "default" | "danger"

export type ConfirmOptions = {
  /** Main message. Rendered as the dialog heading. */
  title: string
  /** Optional secondary line under the heading. */
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** `danger` tints the confirm button red for destructive actions. */
  tone?: ConfirmTone
}

export type AlertOptions = {
  title: string
  description?: ReactNode
  confirmLabel?: string
}

export type PromptOptions = {
  title: string
  description?: ReactNode
  defaultValue?: string
  placeholder?: string
  inputType?: "text" | "number" | "url"
  confirmLabel?: string
  cancelLabel?: string
}

export type ConfirmRequest =
  | { kind: "confirm"; options: ConfirmOptions; resolve: (value: boolean) => void }
  | { kind: "alert"; options: AlertOptions; resolve: () => void }
  | { kind: "prompt"; options: PromptOptions; resolve: (value: string | null) => void }

const queue: ConfirmRequest[] = []
const listeners = new Set<() => void>()
let snapshot: ConfirmRequest | null = null

function publish() {
  snapshot = queue[0] ?? null
  for (const listener of listeners) listener()
}

/** Subscribe to the active dialog request (used by the host component). */
export function subscribeConfirmDialogs(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** The request at the head of the queue, or null when nothing is open. */
export function getActiveConfirmDialog(): ConfirmRequest | null {
  return snapshot
}

/**
 * Resolve the active request: `true`/`false` for a confirm, the entered string
 * (or null) for a prompt, ignored for an alert. Advances the queue.
 */
export function settleConfirmDialog(result: boolean | string | null) {
  const current = queue.shift()
  if (!current) return
  if (current.kind === "confirm") {
    current.resolve(result === true)
  } else if (current.kind === "prompt") {
    current.resolve(typeof result === "string" ? result : null)
  } else {
    current.resolve()
  }
  publish()
}

function enqueue(request: ConfirmRequest) {
  queue.push(request)
  publish()
}

/** Themed replacement for `window.confirm`. Resolves `true` when confirmed. */
export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    enqueue({ kind: "confirm", options, resolve })
  })
}

/** Themed replacement for `window.alert`. Resolves once dismissed. */
export function alertDialog(options: AlertOptions): Promise<void> {
  return new Promise((resolve) => {
    enqueue({ kind: "alert", options, resolve })
  })
}

/**
 * Themed replacement for `window.prompt`. Resolves the entered string, or
 * `null` when the user cancels/dismisses the dialog.
 */
export function promptDialog(options: PromptOptions): Promise<string | null> {
  return new Promise((resolve) => {
    enqueue({ kind: "prompt", options, resolve })
  })
}
