"use client"

// Renders the active queued confirm/alert/prompt from `@/lib/ui/confirm-dialog`
// as a centred frosted-glass dialog. Mounted once in the root layout.

import * as React from "react"

import { cn } from "@/lib/utils"
import {
  getActiveConfirmDialog,
  settleConfirmDialog,
  subscribeConfirmDialogs,
} from "@/lib/ui/confirm-dialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"

export function ConfirmDialogHost() {
  const request = React.useSyncExternalStore(
    subscribeConfirmDialogs,
    getActiveConfirmDialog,
    () => null,
  )
  const [value, setValue] = React.useState("")
  const activeRef = React.useRef<typeof request>(null)

  React.useEffect(() => {
    activeRef.current = request
  }, [request])

  React.useEffect(() => {
    setValue(request?.kind === "prompt" ? request.options.defaultValue ?? "" : "")
  }, [request])

  if (!request) return null

  const options = request.options
  const isPrompt = request.kind === "prompt"
  const isConfirm = request.kind === "confirm"
  const confirmLabel = options.confirmLabel ?? (isConfirm ? "Confirm" : "OK")
  const cancelLabel =
    (request.kind === "confirm" || request.kind === "prompt"
      ? request.options.cancelLabel
      : undefined) ?? "Cancel"
  const danger = request.kind === "confirm" && request.options.tone === "danger"

  // Guard against a second settle (e.g. Enter + click, or a fast double click)
  // consuming the NEXT queued dialog.
  const settle = (result: boolean | string | null) => {
    if (!activeRef.current) return
    activeRef.current = null
    settleConfirmDialog(result)
  }
  const cancel = () => settle(isConfirm ? false : null)
  const accept = () => settle(isPrompt ? value : true)

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) cancel()
      }}
    >
      <DialogContent
        showCloseButton={false}
        overlayClassName="z-[200]"
        className="z-[200] gap-4 rounded-2xl border-white/10 p-5 sm:max-w-md"
      >
        <div className="flex flex-col gap-1.5 pr-1">
          <DialogTitle className="text-sm leading-snug font-semibold text-foreground">
            {options.title}
          </DialogTitle>
          {options.description ? (
            <DialogDescription className="text-[12px] leading-relaxed whitespace-pre-line text-muted-foreground">
              {options.description}
            </DialogDescription>
          ) : null}
        </div>

        {isPrompt ? (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              accept()
            }}
          >
            <Input
              autoFocus
              type={request.options.inputType ?? "text"}
              value={value}
              placeholder={request.options.placeholder}
              onChange={(event) => setValue(event.target.value)}
              onFocus={(event) => event.target.select()}
            />
            <button type="submit" className="hidden" aria-hidden tabIndex={-1} />
          </form>
        ) : null}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          {isConfirm || isPrompt ? (
            <Button variant="ghost" onClick={cancel}>
              {cancelLabel}
            </Button>
          ) : null}
          <Button
            autoFocus={!isPrompt}
            variant={danger ? "destructive" : "default"}
            className={cn(danger && "shadow-[0_0_18px_-6px_rgba(244,63,94,0.6)]")}
            onClick={accept}
          >
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
