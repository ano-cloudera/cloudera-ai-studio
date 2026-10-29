import { jsPDF } from 'jspdf'
import autoTable from 'jspdf-autotable'
import type { ChatResponse } from '../types/api'
import type { StoredMessage } from './chatSessions'
import { formatAnswerParagraphs } from './answerFormatting'
import { answerPresentation } from './governedEvidence'

const A4_WIDTH_MM = 210
const A4_HEIGHT_MM = 297
const MARGIN_MM = 16
const FOOTER_Y_MM = A4_HEIGHT_MM - 10
/** Last Y coordinate available for body content (above footer rule). */
const CONTENT_BOTTOM_MM = FOOTER_Y_MM - 6
/** jspdf-autotable `margin.bottom`: reserved space measured from the page bottom edge. */
const TABLE_BOTTOM_MARGIN_MM = A4_HEIGHT_MM - CONTENT_BOTTOM_MM
const CONTENT_WIDTH_MM = A4_WIDTH_MM - MARGIN_MM * 2
const MAX_TABLE_ROWS = 35
const MAX_CELL_CHARS = 42
const CHART_CAPTURE_WIDTH_PX = 720
const MAX_CHART_HEIGHT_MM = 95
const MIN_BLOCK_MM = 14

const GAP_XS = 2
const GAP_SM = 4
const GAP_MD = 6
const GAP_LG = 10
const GAP_TURN = 12

const INK: [number, number, number] = [18, 0, 94]
const ORANGE: [number, number, number] = [249, 103, 2]
const MUTED: [number, number, number] = [100, 116, 139]
const SLATE: [number, number, number] = [51, 65, 85]
const LINE: [number, number, number] = [230, 228, 238]
const USER_FILL: [number, number, number] = [255, 247, 237]

type JsPdfWithAutoTable = jsPDF & { lastAutoTable?: { finalY: number } }

export function conversationPdfFilename(title: string): string {
  const safeTitle = title.replace(/[^\w\s-]+/g, '').trim().replace(/\s+/g, '-').slice(0, 48) || 'conversation'
  const stamp = new Date().toISOString().slice(0, 10)
  return `ai-studio-${safeTitle}-${stamp}.pdf`
}

export type ConversationPdfInput = {
  title: string
  messages: StoredMessage[]
  appName?: string
  chartRoot?: HTMLElement | null
}

type PdfCursor = { y: number }

function formatExportTimestamp(date: Date): string {
  return date.toLocaleString('id-ID', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatCellValue(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value.toLocaleString('id-ID', { maximumFractionDigits: 2 })
  }
  const text = String(value).replace(/\s+/g, ' ').trim()
  if (text.length <= MAX_CELL_CHARS) return text
  return `${text.slice(0, MAX_CELL_CHARS - 1)}…`
}

function humanColumnHeader(col: string): string {
  return col
    .replace(/_/g, ' ')
    .replace(/\b\w/g, ch => ch.toUpperCase())
}

function formatStrategyLabel(strategy: string): string {
  const labels: Record<string, string> = {
    governed: 'Governed query',
    sql_fallback: 'SQL fallback',
    history_only_analysis: 'Prior-turn analysis',
    conversational: 'Conversation',
    clarification: 'Clarification',
    unsupported: 'Unsupported',
    local_agent_exploratory: 'Exploratory',
  }
  return labels[strategy] ?? strategy.replace(/_/g, ' ')
}

function ensureSpace(pdf: jsPDF, cursor: PdfCursor, neededMm: number, drawRunningHeader?: () => void): void {
  if (cursor.y + neededMm <= CONTENT_BOTTOM_MM) return
  pdf.addPage()
  cursor.y = MARGIN_MM + 4
  drawRunningHeader?.()
}

/** Prefer starting a new turn on a clean page when little room remains. */
function ensureTurnStart(pdf: jsPDF, cursor: PdfCursor, drawRunningHeader?: () => void): void {
  const remaining = CONTENT_BOTTOM_MM - cursor.y
  if (remaining < 48 && cursor.y > MARGIN_MM + 20) {
    pdf.addPage()
    cursor.y = MARGIN_MM + 4
    drawRunningHeader?.()
  }
}

function drawPageFooters(pdf: jsPDF, appName: string): void {
  const total = pdf.getNumberOfPages()
  for (let page = 1; page <= total; page += 1) {
    pdf.setPage(page)
    pdf.setDrawColor(...LINE)
    pdf.setLineWidth(0.2)
    pdf.line(MARGIN_MM, FOOTER_Y_MM - 4, A4_WIDTH_MM - MARGIN_MM, FOOTER_Y_MM - 4)
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(8)
    pdf.setTextColor(...MUTED)
    pdf.text(appName, MARGIN_MM, FOOTER_Y_MM)
    pdf.text(`Halaman ${page} / ${total}`, A4_WIDTH_MM - MARGIN_MM, FOOTER_Y_MM, { align: 'right' })
  }
}

function drawDocumentHeader(
  pdf: jsPDF,
  cursor: PdfCursor,
  title: string,
  appName: string,
  exportedAt: Date,
  compact = false,
): void {
  const startY = cursor.y
  pdf.setFillColor(...ORANGE)
  pdf.rect(MARGIN_MM, startY, CONTENT_WIDTH_MM, 1, 'F')
  cursor.y = startY + (compact ? 5 : 6)

  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(compact ? 9 : 15)
  pdf.setTextColor(...INK)
  pdf.text(appName, MARGIN_MM, cursor.y)
  cursor.y += compact ? 4 : 6

  if (!compact) {
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(9)
    pdf.setTextColor(...MUTED)
    pdf.text(`Diekspor ${formatExportTimestamp(exportedAt)}`, MARGIN_MM, cursor.y)
    cursor.y += 5
  }

  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(compact ? 10 : 12)
  pdf.setTextColor(...SLATE)
  const titleLines = pdf.splitTextToSize(title, CONTENT_WIDTH_MM) as string[]
  const maxTitleLines = compact ? 1 : 3
  const clipped = titleLines.slice(0, maxTitleLines)
  if (titleLines.length > maxTitleLines) {
    const last = clipped[clipped.length - 1] ?? ''
    clipped[clipped.length - 1] = `${last.replace(/\s+\S*$/, '')}…`
  }
  pdf.text(clipped, MARGIN_MM, cursor.y)
  cursor.y += clipped.length * (compact ? 4.5 : 5.5) + (compact ? GAP_SM : GAP_MD)

  pdf.setDrawColor(...LINE)
  pdf.setLineWidth(0.25)
  pdf.line(MARGIN_MM, cursor.y, A4_WIDTH_MM - MARGIN_MM, cursor.y)
  cursor.y += compact ? GAP_MD : GAP_LG
}

function drawSectionLabel(pdf: jsPDF, cursor: PdfCursor, label: string): void {
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(8.5)
  pdf.setTextColor(...ORANGE)
  pdf.text(label.toUpperCase(), MARGIN_MM, cursor.y)
  cursor.y += 4.5
}

function lineHeightForFont(fontSize: number): number {
  return fontSize * 0.42 + 2
}

function drawBodyText(
  pdf: jsPDF,
  cursor: PdfCursor,
  text: string,
  options: { fontSize?: number; bold?: boolean; color?: [number, number, number]; indent?: number } = {},
  drawRunningHeader?: () => void,
): void {
  const fontSize = options.fontSize ?? 10
  const indent = options.indent ?? 0
  const width = CONTENT_WIDTH_MM - indent
  pdf.setFont('helvetica', options.bold ? 'bold' : 'normal')
  pdf.setFontSize(fontSize)
  pdf.setTextColor(...(options.color ?? SLATE))
  const lines = pdf.splitTextToSize(text, width) as string[]
  const lineHeight = lineHeightForFont(fontSize)
  for (const line of lines) {
    ensureSpace(pdf, cursor, lineHeight + 1, drawRunningHeader)
    pdf.text(line, MARGIN_MM + indent, cursor.y)
    cursor.y += lineHeight
  }
  cursor.y += GAP_XS
}

function drawBulletList(pdf: jsPDF, cursor: PdfCursor, items: string[], drawRunningHeader?: () => void): void {
  for (const item of items) {
    drawBodyText(pdf, cursor, `• ${item}`, { indent: 3, fontSize: 9.5 }, drawRunningHeader)
  }
}

function drawTurnRule(pdf: jsPDF, cursor: PdfCursor): void {
  cursor.y += GAP_SM
  pdf.setDrawColor(...LINE)
  pdf.setLineWidth(0.15)
  pdf.line(MARGIN_MM, cursor.y, A4_WIDTH_MM - MARGIN_MM, cursor.y)
  cursor.y += GAP_TURN
}

function drawUserTurn(
  pdf: jsPDF,
  cursor: PdfCursor,
  question: string,
  turnIndex: number,
  drawRunningHeader: () => void,
): void {
  ensureTurnStart(pdf, cursor, drawRunningHeader)
  ensureSpace(pdf, cursor, MIN_BLOCK_MM, drawRunningHeader)
  drawSectionLabel(pdf, cursor, `Pertanyaan ${turnIndex}`)

  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(10)
  const innerWidth = CONTENT_WIDTH_MM - 8
  const lines = pdf.splitTextToSize(question.trim(), innerWidth) as string[]
  const lineHeight = 5
  const boxHeight = lines.length * lineHeight + 8
  ensureSpace(pdf, cursor, boxHeight + GAP_MD, drawRunningHeader)

  const boxTop = cursor.y
  pdf.setFillColor(...USER_FILL)
  pdf.setDrawColor(...ORANGE)
  pdf.setLineWidth(0.2)
  pdf.roundedRect(MARGIN_MM, boxTop, CONTENT_WIDTH_MM, boxHeight, 1.5, 1.5, 'FD')
  pdf.setTextColor(...INK)
  let textY = boxTop + 5
  for (const line of lines) {
    pdf.text(line, MARGIN_MM + 4, textY)
    textY += lineHeight
  }
  cursor.y = boxTop + boxHeight + GAP_MD
}

function drawProseBlocks(
  pdf: jsPDF,
  cursor: PdfCursor,
  text: string,
  omitTables: boolean,
  drawRunningHeader: () => void,
  emphasisFirst = false,
): void {
  const paragraphs = formatAnswerParagraphs(text, { omitTables })
  paragraphs.forEach((paragraph, index) => {
    drawBodyText(
      pdf,
      cursor,
      paragraph,
      {
        fontSize: emphasisFirst && index === 0 ? 10.5 : 9.5,
        bold: emphasisFirst && index === 0,
      },
      drawRunningHeader,
    )
  })
}

function drawMetaLine(pdf: jsPDF, cursor: PdfCursor, response: ChatResponse, drawRunningHeader: () => void): void {
  const presentation = answerPresentation(response)
  const bits = [
    presentation.title,
    response.status,
    formatStrategyLabel(response.strategy),
    `${response.data.row_count.toLocaleString('id-ID')} baris`,
  ].filter(Boolean)
  ensureSpace(pdf, cursor, 8, drawRunningHeader)
  pdf.setFillColor(248, 250, 252)
  pdf.setDrawColor(...LINE)
  pdf.setLineWidth(0.15)
  const metaH = 6
  pdf.rect(MARGIN_MM, cursor.y - 3.5, CONTENT_WIDTH_MM, metaH, 'FD')
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(7.5)
  pdf.setTextColor(...MUTED)
  pdf.text(bits.join('  ·  '), MARGIN_MM + 3, cursor.y)
  cursor.y += GAP_MD
}

function drawDataTable(
  pdf: jsPDF,
  cursor: PdfCursor,
  response: ChatResponse,
  drawRunningHeader: () => void,
): void {
  const { columns, rows } = response.data
  if (!columns.length || !rows.length) return

  const slice = rows.slice(0, MAX_TABLE_ROWS)
  const head = [columns.map(col => humanColumnHeader(col))]
  const body = slice.map(row => columns.map(col => formatCellValue(row[col])))

  ensureSpace(pdf, cursor, 22, drawRunningHeader)
  drawSectionLabel(pdf, cursor, 'Tabel data')
  const tableTop = cursor.y

  autoTable(pdf, {
    startY: tableTop,
    margin: { left: MARGIN_MM, right: MARGIN_MM, bottom: TABLE_BOTTOM_MARGIN_MM },
    tableWidth: CONTENT_WIDTH_MM,
    head,
    body,
    theme: 'grid',
    styles: {
      font: 'helvetica',
      fontSize: 7.5,
      cellPadding: 2.2,
      textColor: SLATE,
      lineColor: LINE,
      lineWidth: 0.12,
      overflow: 'linebreak',
      valign: 'middle',
    },
    headStyles: {
      fillColor: INK,
      textColor: [255, 255, 255],
      fontStyle: 'bold',
      fontSize: 7.5,
    },
    alternateRowStyles: { fillColor: [252, 252, 253] },
  })

  const finalY = (pdf as JsPdfWithAutoTable).lastAutoTable?.finalY ?? tableTop
  cursor.y = finalY + GAP_SM

  if (rows.length > MAX_TABLE_ROWS) {
    drawBodyText(
      pdf,
      cursor,
      `Menampilkan ${MAX_TABLE_ROWS} dari ${rows.length.toLocaleString('id-ID')} baris.`,
      { fontSize: 7.5, color: MUTED },
      drawRunningHeader,
    )
  }
}

function shouldDrawKpi(response: ChatResponse): boolean {
  const spec = response.chart_spec
  if (!spec || spec.type !== 'kpi') return false
  const field = spec.y || response.data.columns[0]
  const raw = field ? response.data.rows[0]?.[field] : undefined
  if (raw == null || raw === '') return false
  if (typeof raw === 'number' && raw === 0 && response.data.rows.length === 1) return false
  return true
}

function drawKpi(pdf: jsPDF, cursor: PdfCursor, response: ChatResponse, drawRunningHeader: () => void): void {
  if (!shouldDrawKpi(response)) return
  const spec = response.chart_spec!
  const field = spec.y || response.data.columns[0]
  const raw = field ? response.data.rows[0]?.[field] : undefined
  ensureSpace(pdf, cursor, 12, drawRunningHeader)
  drawSectionLabel(pdf, cursor, 'Metrik utama')
  drawBodyText(pdf, cursor, `${spec.title}: ${formatCellValue(raw)}`, { bold: true, fontSize: 10 }, drawRunningHeader)
}

async function drawChartSnapshot(
  pdf: jsPDF,
  cursor: PdfCursor,
  node: HTMLElement,
  drawRunningHeader: () => void,
): Promise<void> {
  const { default: html2canvas } = await import('html2canvas')
  const canvas = await html2canvas(node, {
    scale: 2,
    backgroundColor: '#ffffff',
    useCORS: true,
    logging: false,
    width: CHART_CAPTURE_WIDTH_PX,
    windowWidth: CHART_CAPTURE_WIDTH_PX,
  })
  const imgData = canvas.toDataURL('image/png')
  let imgWidthMm = CONTENT_WIDTH_MM
  let imgHeightMm = (canvas.height * imgWidthMm) / canvas.width
  if (imgHeightMm > MAX_CHART_HEIGHT_MM) {
    imgHeightMm = MAX_CHART_HEIGHT_MM
    imgWidthMm = (canvas.width * imgHeightMm) / canvas.height
    const xOffset = MARGIN_MM + (CONTENT_WIDTH_MM - imgWidthMm) / 2
    ensureSpace(pdf, cursor, imgHeightMm + 12, drawRunningHeader)
    drawSectionLabel(pdf, cursor, 'Grafik')
    pdf.addImage(imgData, 'PNG', xOffset, cursor.y, imgWidthMm, imgHeightMm)
    cursor.y += imgHeightMm + GAP_MD
    return
  }

  ensureSpace(pdf, cursor, imgHeightMm + 12, drawRunningHeader)
  drawSectionLabel(pdf, cursor, 'Grafik')
  pdf.addImage(imgData, 'PNG', MARGIN_MM, cursor.y, imgWidthMm, imgHeightMm)
  cursor.y += imgHeightMm + GAP_MD
}

function drawCaveats(
  pdf: jsPDF,
  cursor: PdfCursor,
  caveats: string[],
  drawRunningHeader: () => void,
): void {
  if (!caveats.length) return
  ensureSpace(pdf, cursor, MIN_BLOCK_MM, drawRunningHeader)
  drawSectionLabel(pdf, cursor, 'Catatan data')
  drawBulletList(pdf, cursor, caveats, drawRunningHeader)
}

async function drawAssistantTurn(
  pdf: jsPDF,
  cursor: PdfCursor,
  response: ChatResponse,
  fallbackText: string,
  turnIndex: number,
  drawRunningHeader: () => void,
  chartNode?: HTMLElement | null,
): Promise<void> {
  ensureSpace(pdf, cursor, MIN_BLOCK_MM, drawRunningHeader)
  drawSectionLabel(pdf, cursor, `Jawaban ${turnIndex}`)
  drawMetaLine(pdf, cursor, response, drawRunningHeader)

  const omitTables = response.data.rows.length > 0
  const narrative = response.answer.direct_answer.trim() || fallbackText.trim()
  drawProseBlocks(pdf, cursor, narrative, omitTables, drawRunningHeader, true)

  drawKpi(pdf, cursor, response, drawRunningHeader)

  const visualTypes = ['bar', 'line', 'area', 'scatter', 'pie']
  const hasVisualChart = Boolean(
    response.chart_spec &&
      visualTypes.includes(response.chart_spec.type) &&
      response.chart_spec.x &&
      response.chart_spec.y &&
      response.data.rows.length > 0,
  )

  if (hasVisualChart && chartNode) {
    try {
      await drawChartSnapshot(pdf, cursor, chartNode, drawRunningHeader)
    } catch (err) {
      console.warn('conversation_pdf_chart_snapshot_skipped', err)
      drawBodyText(
        pdf,
        cursor,
        'The chart could not be included in the PDF; use the data table below.',
        { fontSize: 8, color: MUTED },
        drawRunningHeader,
      )
    }
  }

  drawDataTable(pdf, cursor, response, drawRunningHeader)

  const summary = response.answer.executive_summary.trim()
  if (summary && summary !== response.answer.direct_answer.trim()) {
    ensureSpace(pdf, cursor, MIN_BLOCK_MM, drawRunningHeader)
    drawSectionLabel(pdf, cursor, 'Analisa')
    drawProseBlocks(pdf, cursor, summary, omitTables, drawRunningHeader)
  }

  if (response.answer.insights.length) {
    ensureSpace(pdf, cursor, MIN_BLOCK_MM, drawRunningHeader)
    drawSectionLabel(pdf, cursor, 'Insight')
    drawBulletList(pdf, cursor, response.answer.insights, drawRunningHeader)
  }

  if (response.answer.business_implications.length) {
    ensureSpace(pdf, cursor, MIN_BLOCK_MM, drawRunningHeader)
    drawSectionLabel(pdf, cursor, 'Implikasi bisnis')
    drawBulletList(pdf, cursor, response.answer.business_implications, drawRunningHeader)
  }
  drawCaveats(pdf, cursor, response.answer.caveats, drawRunningHeader)
  drawTurnRule(pdf, cursor)
}

function assistantChartNode(
  response: ChatResponse,
  chartNodes: HTMLElement[],
  chartNodeIndex: number,
): HTMLElement | null {
  const visualTypes = ['bar', 'line', 'area', 'scatter', 'pie']
  const hasVisualChart = Boolean(
    response.chart_spec &&
      visualTypes.includes(response.chart_spec.type) &&
      response.chart_spec.x &&
      response.chart_spec.y &&
      response.data.rows.length > 0,
  )
  if (!hasVisualChart) return null
  return chartNodes[chartNodeIndex] ?? null
}

export async function downloadConversationPdf(input: ConversationPdfInput): Promise<void> {
  const { title, messages, appName, chartRoot } = input
  const resolvedAppName = appName ?? 'Ask Data export'
  if (!messages.length) return

  const exportedAt = new Date()
  const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4' })
  const cursor: PdfCursor = { y: MARGIN_MM }
  const runningHeader = () => drawDocumentHeader(pdf, cursor, title, resolvedAppName, exportedAt, true)

  drawDocumentHeader(pdf, cursor, title, resolvedAppName, exportedAt)

  const chartNodes = chartRoot ? [...chartRoot.querySelectorAll<HTMLElement>('[data-pdf-export-chart]')] : []
  let chartNodeIndex = 0
  let turnIndex = 0

  for (const message of messages) {
    if (message.role === 'user') {
      turnIndex += 1
      drawUserTurn(pdf, cursor, message.content, turnIndex, runningHeader)
      continue
    }

    if (message.response) {
      const chartNode = assistantChartNode(message.response, chartNodes, chartNodeIndex)
      if (chartNode) chartNodeIndex += 1
      await drawAssistantTurn(
        pdf,
        cursor,
        message.response,
        message.content,
        turnIndex || 1,
        runningHeader,
        chartNode,
      )
    } else {
      ensureSpace(pdf, cursor, MIN_BLOCK_MM, runningHeader)
      drawSectionLabel(pdf, cursor, `Jawaban ${turnIndex || 1}`)
      drawBodyText(pdf, cursor, message.content, {}, runningHeader)
      drawTurnRule(pdf, cursor)
    }
  }

  drawPageFooters(pdf, resolvedAppName)
  pdf.save(conversationPdfFilename(title))
}
