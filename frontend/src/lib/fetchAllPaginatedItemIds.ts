type PaginatedPage<T extends { id: string }> = {
  items: T[]
  total: number
  total_pages?: number
}

/** Walk paginated list APIs (page_size capped server-side) and return every matching id. */
export async function fetchAllPaginatedItemIds<T extends { id: string }>(
  fetchPage: (page: number, pageSize: number) => Promise<PaginatedPage<T>>,
  pageSize = 100,
): Promise<string[]> {
  const ids: string[] = []
  let page = 1
  let totalPages = 1
  do {
    const result = await fetchPage(page, pageSize)
    ids.push(...result.items.map(item => item.id))
    totalPages =
      result.total_pages ?? Math.max(1, Math.ceil(result.total / pageSize))
    page += 1
  } while (page <= totalPages)
  return ids
}
