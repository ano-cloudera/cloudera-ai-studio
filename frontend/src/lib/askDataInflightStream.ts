import type { ChatResponse, ModelSelection } from '../types/api'
import { api } from './api'
import type { ProcessSnapshot, StoredMessage } from './chatSessions'
import { saveSession, sessionTitle } from './chatSessions'
import { DETAILED_PROGRESS_STEPS, mergeProgressStep, type ProgressTraceEntry } from './streamProgress'

export type InflightStreamSnapshot = {
  sessionId: string
  loading: boolean
  progressStep: number
  technicalTrace: ProgressTraceEntry[]
  error: string
}

type Listener = (snapshot: InflightStreamSnapshot) => void

let snapshot: InflightStreamSnapshot = {
  sessionId: '',
  loading: false,
  progressStep: 0,
  technicalTrace: [],
  error: '',
}

let listeners = new Set<Listener>()
let abortController: AbortController | null = null

function emit() {
  const copy = { ...snapshot, technicalTrace: [...snapshot.technicalTrace] }
  listeners.forEach(l => l(copy))
}

export function subscribeInflightStream(listener: Listener): () => void {
  listeners.add(listener)
  listener({ ...snapshot })
  return () => listeners.delete(listener)
}

export function inflightStreamSessionId(): string | null {
  return snapshot.loading ? snapshot.sessionId : null
}

export function abortInflightStream(): void {
  abortController?.abort()
}

type StartArgs = {
  sessionId: string
  selection: ModelSelection
  question: string
  userMessage: StoredMessage
  priorMessages: StoredMessage[]
  streamTimeoutMs: number
  contextPayload:
    | { mode: 'ask_data' }
    | {
        context_sources: Array<{ type: string; id: string; name: string }>
      }
  onDone?: (response: ChatResponse) => void
}

export function startInflightStream(args: StartArgs): void {
  if (snapshot.loading) {
    abortInflightStream()
  }

  const progressLive = { step: 0, trace: [] as ProgressTraceEntry[] }
  snapshot = {
    sessionId: args.sessionId,
    loading: true,
    progressStep: 0,
    technicalTrace: [],
    error: '',
  }
  emit()

  const messagesAfterUser = [...args.priorMessages, args.userMessage]
  saveSession({
    id: args.sessionId,
    title: sessionTitle(messagesAfterUser),
    updatedAt: Date.now(),
    messages: messagesAfterUser,
    selection: args.selection,
  })

  const controller = new AbortController()
  abortController = controller
  let timedOut = false
  const timeout = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, args.streamTimeoutMs)

  void (async () => {
    let streamSucceeded = false
    try {
      for await (const event of api.chatStream(
        args.question,
        args.sessionId,
        args.selection,
        controller.signal,
        args.contextPayload,
      )) {
        if (event.type === 'progress') {
          progressLive.step = mergeProgressStep(progressLive.step, event.stage, event.label)
          const entry: ProgressTraceEntry = {
            stage: event.stage,
            label: event.label,
            detail: event.detail,
          }
          const key = `${entry.stage}|${entry.label}|${entry.detail ?? ''}`
          const last = progressLive.trace[progressLive.trace.length - 1]
          const lastKey = last ? `${last.stage}|${last.label}|${last.detail ?? ''}` : ''
          if (key !== lastKey) progressLive.trace = [...progressLive.trace, entry]
          snapshot = {
            ...snapshot,
            progressStep: progressLive.step,
            technicalTrace: [...progressLive.trace],
          }
          emit()
          continue
        }
        if (event.type === 'done') {
          streamSucceeded = true
          const finalStep = Math.max(progressLive.step, DETAILED_PROGRESS_STEPS.length - 1)
          const processSnapshot: ProcessSnapshot = {
            activeStepIndex: finalStep,
            technicalTrace: [...progressLive.trace],
          }
          const assistantMessage: StoredMessage = {
            role: 'assistant',
            content: event.response.answer.executive_summary,
            response: event.response,
            processSnapshot,
          }
          const fullMessages = [...messagesAfterUser, assistantMessage]
          saveSession({
            id: args.sessionId,
            title: sessionTitle(fullMessages),
            updatedAt: Date.now(),
            messages: fullMessages,
            selection: args.selection,
          })
          args.onDone?.(event.response)
          snapshot = {
            sessionId: args.sessionId,
            loading: false,
            progressStep: 0,
            technicalTrace: [],
            error: '',
          }
          emit()
          break
        }
      }
    } catch (caught) {
      const message =
        caught instanceof DOMException && caught.name === 'AbortError'
          ? timedOut
            ? 'Request timed out. Please try again.'
            : 'Request stopped.'
          : 'Unable to complete the analysis right now. Please try again.'
      if (!streamSucceeded) {
        snapshot = {
          ...snapshot,
          loading: false,
          progressStep: 0,
          technicalTrace: [],
          error: message,
        }
        emit()
      }
    } finally {
      window.clearTimeout(timeout)
      if (abortController === controller) abortController = null
      if (snapshot.loading && snapshot.sessionId === args.sessionId) {
        snapshot = { ...snapshot, loading: false, progressStep: 0, technicalTrace: [] }
        emit()
      }
    }
  })()
}
