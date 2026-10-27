'use client'

import { useMemo, useRef, useState } from 'react'
import { ChatComposer } from '../ChatComposer'
import type { ChatContextSource } from '../../lib/chatContext'
import { mergeKnowledgeLibraryContext, removeContextSource } from '../../lib/chatContext'
import { AttachedContextChips } from './AttachedContextChips'
import { ComposerAddMenu } from './ComposerAddMenu'
import {
  ContextPicker,
  contextPickerFilterQuery,
  filterContextPickerOptions,
  handleContextPickerKeyDown,
  type ContextPickerOption,
} from './ContextPicker'

type Props = {
  value: string
  loading: boolean
  disabled: boolean
  modelHint?: string | null
  contextSources: ChatContextSource[]
  contextOptions: ContextPickerOption[]
  allowMultipleLibraries?: boolean
  onChange: (value: string) => void
  onContextChange: (sources: ChatContextSource[]) => void
  onSubmit: (question: string) => void
  onStop: () => void
  composerRef?: React.RefObject<HTMLTextAreaElement | null>
  onUploadFiles: (files: File[]) => void
  onRetryAttachment?: (id: string) => void
  onSaveToKnowledge?: (id: string, name: string) => void
  submitDisabledReason?: string | null
}

function mentionState(value: string, caret: number) {
  const before = value.slice(0, caret)
  const match = before.match(/@([^\s@]*)$/)
  if (!match) return null
  return { query: match[1] ?? '', start: before.length - match[0].length }
}

export function ContextAwareChatComposer({
  value,
  loading,
  disabled,
  modelHint,
  contextSources,
  contextOptions,
  allowMultipleLibraries = true,
  onChange,
  onContextChange,
  onSubmit,
  onStop,
  composerRef,
  onUploadFiles,
  onRetryAttachment,
  onSaveToKnowledge,
  submitDisabledReason,
}: Props) {
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const uploadInputRef = useRef<HTMLInputElement>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [mentionQuery, setMentionQuery] = useState('')
  const [pickerSearchText, setPickerSearchText] = useState('')
  const [mentionStart, setMentionStart] = useState<number | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const internalRef = useRef<HTMLTextAreaElement>(null)
  const textareaRef = composerRef ?? internalRef

  const pickerFilterQuery = useMemo(
    () => contextPickerFilterQuery(mentionQuery, pickerSearchText),
    [mentionQuery, pickerSearchText],
  )

  const filteredOptions = useMemo(
    () => filterContextPickerOptions(contextOptions, pickerFilterQuery),
    [contextOptions, pickerFilterQuery],
  )

  const filteredCount = filteredOptions.length

  function syncMention(nextValue: string, caret: number) {
    const state = mentionState(nextValue, caret)
    if (!state) {
      setPickerOpen(false)
      setMentionQuery('')
      setPickerSearchText('')
      setMentionStart(null)
      return
    }
    setPickerOpen(true)
    setMentionQuery(state.query)
    setMentionStart(state.start)
    setActiveIndex(0)
  }

  function openKnowledgePicker() {
    const suffix = value.trim().length ? `${value.trimEnd()} @` : '@'
    onChange(suffix)
    setPickerOpen(true)
    setMentionQuery('')
    setPickerSearchText('')
    setMentionStart(suffix.lastIndexOf('@'))
    setActiveIndex(0)
    window.setTimeout(() => textareaRef.current?.focus(), 0)
  }

  function selectSource(source: ChatContextSource) {
    onContextChange(
      mergeKnowledgeLibraryContext(contextSources, source, { allowMultiple: allowMultipleLibraries }),
    )
    if (mentionStart != null) {
      const caret = textareaRef.current?.selectionStart ?? value.length
      const after = value.slice(caret)
      const prefix = value.slice(0, mentionStart)
      onChange(`${prefix}${after}`.trimStart())
    }
    setPickerOpen(false)
    setMentionQuery('')
    setPickerSearchText('')
    setMentionStart(null)
    textareaRef.current?.focus()
  }

  function closePicker() {
    setPickerOpen(false)
    setPickerSearchText('')
  }

  return (
    <div className="relative w-full" data-testid="chat-composer">
      <AttachedContextChips
        sources={contextSources}
        onRemove={id => onContextChange(removeContextSource(contextSources, id))}
        onRetryAttachment={onRetryAttachment}
        onSaveToKnowledge={onSaveToKnowledge}
      />
      <ContextPicker
        open={pickerOpen}
        query={mentionQuery}
        searchText={pickerSearchText}
        onSearchTextChange={setPickerSearchText}
        options={contextOptions}
        activeIndex={activeIndex}
        onHighlight={setActiveIndex}
        onSelect={selectSource}
        onClose={closePicker}
      />
      <ChatComposer
        value={value}
        loading={loading}
        disabled={disabled || Boolean(submitDisabledReason)}
        modelHint={modelHint}
        submitDisabledReason={submitDisabledReason}
        leadingAction={
          <ComposerAddMenu
            open={addMenuOpen}
            onToggle={() => setAddMenuOpen(current => !current)}
            onClose={() => setAddMenuOpen(false)}
            onKnowledge={openKnowledgePicker}
            onUploadFiles={() => uploadInputRef.current?.click()}
            uploadInputRef={uploadInputRef}
            accept=".pdf,.docx,.txt,.md,.markdown"
            onFilesSelected={list => {
              if (!list?.length) return
              onUploadFiles(Array.from(list))
            }}
          />
        }
        onChange={next => {
          onChange(next)
          const caret = textareaRef.current?.selectionStart ?? next.length
          syncMention(next, caret)
        }}
        onSubmit={() => onSubmit(value.trim())}
        onStop={onStop}
        textareaRef={textareaRef}
        onKeyDown={event => {
          if (
            pickerOpen &&
            handleContextPickerKeyDown(
              event,
              filteredCount,
              activeIndex,
              setActiveIndex,
              index => {
                const picked = filteredOptions[index]
                if (picked) selectSource(picked.source)
              },
              closePicker,
            )
          ) {
            return
          }
          if (event.key === 'Enter' && !event.shiftKey && value.trim() && !loading && !disabled) {
            event.preventDefault()
            onSubmit(value.trim())
          }
        }}
      />
    </div>
  )
}
