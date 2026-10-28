'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  BarChart3,
  BookOpen,
  Bot,
  Cable,
  Download,
  Layers,
  MessageSquareText,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  SquarePen,
  Wand2,
} from 'lucide-react'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { BrandMark } from '../components/BrandMark'
import { ConversationSessionList, type ConversationSessionListProps } from '../components/ConversationSessionList'
import { appConfig } from '../config/appConfig'
import { usePublicBranding } from '../config/PublicBrandingContext'
import { usePlatformReadiness } from '../hooks/usePlatformReadiness'

type NavItem = {
  feature: keyof typeof appConfig.features
  href: string
  label: () => string
  icon: typeof Bot
}

const NAV_SECTIONS: { title?: string; items: NavItem[] }[] = [
  {
    items: [{ feature: 'askData', href: '/', label: () => appConfig.navigationAskData, icon: Bot }],
  },
  {
    title: 'Build',
    items: [
      { feature: 'documents', href: '/knowledge', label: () => appConfig.navigationKnowledge, icon: BookOpen },
      { feature: 'semanticLayer', href: '/semantic-layer', label: () => appConfig.navigationSemanticLayer, icon: Layers },
    ],
  },
  {
    title: 'Context',
    items: [
      { feature: 'prompts', href: '/prompts', label: () => appConfig.navigationPrompts, icon: MessageSquareText },
      { feature: 'skills', href: '/skills', label: () => appConfig.navigationSkills, icon: Wand2 },
      { feature: 'connectors', href: '/connectors', label: () => appConfig.navigationConnectors, icon: Cable },
    ],
  },
  {
    title: 'Monitor',
    items: [{ feature: 'usage', href: '/usage', label: () => appConfig.navigationUsage, icon: BarChart3 }],
  },
  {
    items: [{ feature: 'settings', href: '/settings', label: () => appConfig.navigationSettings, icon: Settings }],
  },
]

export function buildPrimaryNavigation() {
  return NAV_SECTIONS.flatMap(section =>
    section.items
      .filter(item => appConfig.features[item.feature])
      .map(item => ({
        href: item.href,
        label: item.label(),
        icon: item.icon,
        section: section.title,
      })),
  )
}

export function buildSidebarSections() {
  return NAV_SECTIONS.map(section => ({
    title: section.title,
    items: section.items
      .filter(item => appConfig.features[item.feature])
      .map(item => ({
        href: item.href,
        label: item.label(),
        icon: item.icon,
      })),
  })).filter(section => section.items.length > 0)
}

/** Collapsed sidebar: one footprint for logo, toggle, New Chat, and nav icons. */
const COLLAPSED_RAIL_ITEM =
  'grid h-9 w-9 shrink-0 place-items-center rounded-lg transition-colors'

/** Soft Cloudera orange — visible brand tint without solid CTA orange. */
const NEW_CHAT_SURFACE =
  'border border-cloudera-orange/20 bg-cloudera-orange/[0.14] text-cloudera-navy hover:border-cloudera-orange/35 hover:bg-cloudera-orange/[0.22]'

export type ChatSessionSidebarState = Omit<ConversationSessionListProps, 'collapsed'> & {
  onNewChat: () => void
}

export type ChatPageChromeState = {
  showDownload: boolean
  downloadingPdf: boolean
  loading: boolean
  onDownloadPdf: () => void
  /** Hide top header title (e.g. empty Ask Data) so branding stays in the conversation area. */
  minimalHeader?: boolean
}

type ChatLayoutState = {
  sidebarCollapsed: boolean
  toggleSidebarCollapsed: () => void
  chatSessionSidebar: ChatSessionSidebarState | null
  setChatSessionSidebar: (state: ChatSessionSidebarState | null) => void
  chatPageChrome: ChatPageChromeState | null
  setChatPageChrome: (state: ChatPageChromeState | null) => void
}

const ChatLayoutContext = createContext<ChatLayoutState>({
  sidebarCollapsed: false,
  toggleSidebarCollapsed: () => undefined,
  chatSessionSidebar: null,
  setChatSessionSidebar: () => undefined,
  chatPageChrome: null,
  setChatPageChrome: () => undefined,
})

export function useChatLayout() {
  return useContext(ChatLayoutContext)
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const branding = usePublicBranding()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [chatSessionSidebar, setChatSessionSidebarState] = useState<ChatSessionSidebarState | null>(null)
  const [chatPageChrome, setChatPageChromeState] = useState<ChatPageChromeState | null>(null)

  const toggleSidebarCollapsed = useCallback(() => {
    setSidebarCollapsed(current => !current)
  }, [])

  const setChatSessionSidebar = useCallback((state: ChatSessionSidebarState | null) => {
    setChatSessionSidebarState(state)
  }, [])

  const setChatPageChrome = useCallback((state: ChatPageChromeState | null) => {
    setChatPageChromeState(state)
  }, [])

  const navigation = useMemo(() => buildPrimaryNavigation(), [])
  const sidebarSections = useMemo(() => buildSidebarSections(), [])
  const platform = usePlatformReadiness()
  const platformDot =
    platform.status === 'ready' ? 'bg-emerald-500' : platform.status === 'degraded' ? 'bg-amber-500' : 'bg-rose-500'
  const platformLabel =
    platform.status === 'ready'
      ? appConfig.platformStatusLabel
      : platform.status === 'degraded'
        ? 'Platform Degraded'
        : platform.status === 'checking'
          ? 'Checking…'
          : 'Platform Unavailable'

  const layoutValue = useMemo(
    () => ({
      sidebarCollapsed,
      toggleSidebarCollapsed,
      chatSessionSidebar,
      setChatSessionSidebar,
      chatPageChrome,
      setChatPageChrome,
    }),
    [sidebarCollapsed, toggleSidebarCollapsed, chatSessionSidebar, setChatSessionSidebar, chatPageChrome, setChatPageChrome],
  )

  const onAskData = pathname === '/'
  const showChatWorkspace = onAskData && chatSessionSidebar !== null
  const sidebarExpandedClass = sidebarCollapsed ? 'lg:w-[68px]' : 'lg:w-[272px]'
  const mainPadClass = sidebarCollapsed ? 'lg:pl-[68px]' : 'lg:pl-[272px]'

  return (
    <ChatLayoutContext.Provider value={layoutValue}>
      <div className="min-h-screen bg-cloudera-mist text-cloudera-ink">
        <aside
          aria-label="Primary sidebar"
          className={`fixed inset-y-0 left-0 z-30 hidden ${sidebarExpandedClass} flex-col border-r border-slate-200 bg-white transition-[width] duration-300 ease-in-out lg:flex`}
        >
          <div
            className={`flex shrink-0 border-b border-slate-100 ${
              sidebarCollapsed
                ? 'flex-col items-center gap-2 px-2 py-3'
                : 'items-center justify-between gap-2 px-3 py-3'
            }`}
          >
            {!sidebarCollapsed ? (
              <div className="min-w-0 flex-1">
                <BrandMark />
              </div>
            ) : (
              <div
                className={`${COLLAPSED_RAIL_ITEM} border border-slate-100 bg-white shadow-[0_1px_3px_rgba(36,19,95,0.06)]`}
              >
                <img
                  src={branding.logoUrl}
                  alt=""
                  aria-hidden
                  className="h-7 w-7 object-contain"
                />
              </div>
            )}
            <button
              type="button"
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              aria-expanded={!sidebarCollapsed}
              onClick={toggleSidebarCollapsed}
              className={
                sidebarCollapsed
                  ? `${COLLAPSED_RAIL_ITEM} border border-slate-200 text-slate-500 hover:bg-violet-50 hover:text-cloudera-violet`
                  : `${COLLAPSED_RAIL_ITEM} text-slate-500 hover:bg-violet-50 hover:text-cloudera-violet`
              }
            >
              {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          </div>

          <div
            className={`flex min-h-0 flex-1 flex-col ${
              sidebarCollapsed ? 'items-center gap-1 px-2 py-2' : 'px-3 py-2'
            }`}
          >
            {showChatWorkspace && (
              <button
                type="button"
                aria-label="New chat"
                title="New chat"
                onClick={chatSessionSidebar.onNewChat}
                className={
                  sidebarCollapsed
                    ? `${COLLAPSED_RAIL_ITEM} ${NEW_CHAT_SURFACE}`
                    : `type-sidebar-nav mb-2 flex h-9 w-full items-center gap-1.5 rounded-lg px-2 font-medium transition-colors ${NEW_CHAT_SURFACE}`
                }
              >
                {sidebarCollapsed ? (
                  <SquarePen size={17} strokeWidth={1.75} aria-hidden />
                ) : (
                  <>
                    <span className="grid h-7 w-7 shrink-0 place-items-center">
                      <SquarePen size={17} strokeWidth={1.75} aria-hidden />
                    </span>
                    New chat
                  </>
                )}
              </button>
            )}

            <nav
              aria-label="Primary navigation"
              className={`sidebar-primary-nav ${
                sidebarCollapsed ? 'flex w-full flex-col items-center gap-1' : 'w-full space-y-0.5'
              }`}
            >
              {sidebarSections.map((section, sectionIndex) => (
                <div
                  key={section.title ?? `section-${sectionIndex}`}
                  className={
                    sidebarCollapsed
                      ? 'flex flex-col items-center gap-1'
                      : `space-y-px ${sectionIndex > 0 ? 'pt-2' : ''}`
                  }
                >
                  {!sidebarCollapsed && section.title ? (
                    <div className="type-sidebar-section mb-0.5 px-1">{section.title}</div>
                  ) : null}
                  {!sidebarCollapsed && !section.title && sectionIndex === 0 ? (
                    <div className="type-sidebar-section mb-0.5 px-1">Navigation</div>
                  ) : null}
                  {section.items.map(item => {
                    const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href)
                    const Icon = item.icon
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        aria-current={active ? 'page' : undefined}
                        data-active={active ? 'true' : 'false'}
                        title={sidebarCollapsed ? item.label : undefined}
                        className={`sidebar-nav-link type-sidebar-nav ${
                          sidebarCollapsed
                            ? COLLAPSED_RAIL_ITEM
                            : 'flex h-9 items-center gap-1.5 rounded-lg px-2 py-0'
                        }`}
                      >
                        {sidebarCollapsed ? (
                          <Icon size={17} />
                        ) : (
                          <>
                            <span className="grid h-7 w-7 shrink-0 place-items-center">
                              <Icon size={17} />
                            </span>
                            {item.label}
                          </>
                        )}
                      </Link>
                    )
                  })}
                </div>
              ))}
            </nav>

            {showChatWorkspace && chatSessionSidebar && (
              <ConversationSessionList
                collapsed={sidebarCollapsed}
                sessions={chatSessionSidebar.sessions}
                activeSessionId={chatSessionSidebar.activeSessionId}
                onOpenSession={chatSessionSidebar.onOpenSession}
                onRemoveSession={chatSessionSidebar.onRemoveSession}
                onTogglePinSession={chatSessionSidebar.onTogglePinSession}
                onRenameSession={chatSessionSidebar.onRenameSession}
              />
            )}
          </div>

          {!sidebarCollapsed && (
            <div className="shrink-0 border-t border-slate-100 px-3 py-3">
              <div className="flex items-center gap-2">
                <img
                  src={branding.logoUrl}
                  alt=""
                  aria-hidden
                  className="h-5 w-5 shrink-0 rounded object-contain"
                />
                <span className="text-xs font-medium text-slate-600">{branding.sidebarPoweredByLabel}</span>
              </div>
              {branding.sidebarFooterCaption ? (
                <p className="type-chat-meta mt-1.5 leading-snug">{branding.sidebarFooterCaption}</p>
              ) : null}
            </div>
          )}
        </aside>

        <div
          className={`flex h-dvh max-h-dvh flex-col overflow-hidden transition-[padding-left] duration-300 ease-in-out ${mainPadClass}`}
        >
          <header className="z-20 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white/95 px-4 sm:px-5">
            {onAskData && chatPageChrome?.minimalHeader ? (
              <div className="min-w-0 flex-1" aria-hidden />
            ) : (
              <div className="type-app-title min-w-0 truncate">{branding.headerTitle}</div>
            )}
            <div className="flex shrink-0 items-center gap-2">
              <div className="chip py-1" title="Backend platform readiness">
                <span className={`h-2 w-2 rounded-full ${platformDot}`} />
                {platformLabel}
              </div>
              {onAskData && chatPageChrome?.showDownload && (
                <button
                  type="button"
                  aria-label="Download conversation as PDF"
                  disabled={chatPageChrome.downloadingPdf || chatPageChrome.loading}
                  onClick={chatPageChrome.onDownloadPdf}
                  className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 px-2 text-xs font-semibold text-slate-600 transition-colors hover:border-cloudera-orange/40 hover:bg-orange-50/50 disabled:opacity-50"
                >
                  <Download size={14} />
                  <span className="hidden md:inline">{chatPageChrome.downloadingPdf ? 'PDF…' : 'PDF'}</span>
                </button>
              )}
            </div>
          </header>
          <main
            className={`min-h-0 flex-1 ${
              onAskData ? 'flex min-h-0 flex-col overflow-hidden' : 'overflow-y-auto p-4 sm:p-6'
            }`}
          >
            {children}
          </main>
        </div>

        <nav aria-label="Mobile navigation" className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-slate-200 bg-white p-2 lg:hidden">
          {navigation.map(item => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-bold text-cloudera-navy transition-colors hover:bg-violet-50 hover:text-cloudera-violet"
            >
              <item.icon size={16} />
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </ChatLayoutContext.Provider>
  )
}
