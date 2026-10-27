export type SemanticListParams = {
  search?: string
  sort?: string
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
  type?: string
}

export function semanticListQuery(params: SemanticListParams = {}): string {
  const q = new URLSearchParams()
  if (params.search) q.set('search', params.search)
  if (params.sort) q.set('sort', params.sort)
  if (params.order) q.set('order', params.order)
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  if (params.type) q.set('type', params.type)
  const s = q.toString()
  return s ? `?${s}` : ''
}
