'use client'

import { useCallback, useEffect, useState } from 'react'
import { toAppApiError, type AppApiError } from '../../../lib/apiError'
import type { PaginatedMeta, SemanticListParams } from './semanticApiParams'
import { SEMANTIC_DEFAULT_PAGE_SIZE } from './semanticTableConstants'

type FetchResult<T> = { items: T[]; meta?: PaginatedMeta }

export function useSemanticPaginatedList<T>(
  versionId: string | null,
  fetchPage: (versionId: string, params: SemanticListParams) => Promise<FetchResult<T>>,
  deps: unknown[] = [],
) {
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('modified')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(SEMANTIC_DEFAULT_PAGE_SIZE)
  const [items, setItems] = useState<T[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<AppApiError | null>(null)

  const reload = useCallback(async () => {
    if (!versionId) {
      setItems([])
      setTotal(0)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await fetchPage(versionId, {
        search: search.trim() || undefined,
        sort,
        order,
        page,
        page_size: pageSize,
      })
      setItems(result.items)
      setTotal(result.meta?.total ?? result.items.length)
    } catch (err) {
      setError(toAppApiError(err))
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [versionId, fetchPage, search, sort, order, page, pageSize, ...deps])

  useEffect(() => {
    void reload()
  }, [reload])

  function applySort(field: string) {
    if (sort === field) setOrder(o => (o === 'asc' ? 'desc' : 'asc'))
    else {
      setSort(field)
      setOrder(field === 'name' ? 'asc' : 'desc')
    }
    setPage(1)
  }

  return {
    search,
    setSearch: (v: string) => {
      setSearch(v)
      setPage(1)
    },
    sort,
    order,
    applySort,
    page,
    setPage,
    pageSize,
    setPageSize: (n: number) => {
      setPageSize(n)
      setPage(1)
    },
    items,
    total,
    loading,
    error,
    reload,
  }
}
