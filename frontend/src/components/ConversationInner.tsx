'use client'

import type { ReactNode } from 'react'

/** Shared horizontal rail for user, assistant, progress, and composer. */
/** ~48rem centered column — aligned with composer and bubbles (ChatGPT-style). */
export const CONVERSATION_RAIL_CLASS =
  'conversation-rail mx-auto w-full max-w-[min(100%,52rem)] px-4 sm:px-5 lg:max-w-[720px]'

export function conversationRailClassName(extra?: string): string {
  return extra ? `${CONVERSATION_RAIL_CLASS} ${extra}` : CONVERSATION_RAIL_CLASS
}

/** @deprecated alias — same as conversation rail */
export function conversationInnerClassName(extra?: string): string {
  return conversationRailClassName(extra)
}

export function ConversationInner({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={conversationRailClassName(className)}>{children}</div>
}

/** Assistant prose and cards — left-aligned inside the rail, narrower for reading comfort. */
export const ASSISTANT_CONTENT_CLASS = 'w-full min-w-0'

export const ASSISTANT_CHART_CLASS = 'w-full min-w-0'

/** Left-aligned assistant block (no avatar). */
export function AssistantContent({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={className ? `${ASSISTANT_CONTENT_CLASS} ${className}` : ASSISTANT_CONTENT_CLASS}>{children}</div>
}

/** Right-align user bubble against the rail, not the viewport. */
export const USER_MESSAGE_ROW_CLASS = 'flex w-full justify-end'

export const USER_BUBBLE_CLASS =
  'type-chat-user max-w-[min(78%,28rem)] rounded-[18px] rounded-tr-md bg-cloudera-navy px-[15px] py-2.5 text-white max-sm:max-w-[min(88%,100%)]'
