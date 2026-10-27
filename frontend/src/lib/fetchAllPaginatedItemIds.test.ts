import { describe, expect, it, vi } from 'vitest'

import { fetchAllPaginatedItemIds } from './fetchAllPaginatedItemIds'

describe('fetchAllPaginatedItemIds', () => {
  it('walks every page', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({
        items: [{ id: '1' }, { id: '2' }],
        total: 3,
        total_pages: 2,
      })
      .mockResolvedValueOnce({
        items: [{ id: '3' }],
        total: 3,
        total_pages: 2,
      })

    const ids = await fetchAllPaginatedItemIds(fetchPage, 2)
    expect(ids).toEqual(['1', '2', '3'])
    expect(fetchPage).toHaveBeenCalledTimes(2)
    expect(fetchPage).toHaveBeenNthCalledWith(1, 1, 2)
    expect(fetchPage).toHaveBeenNthCalledWith(2, 2, 2)
  })
})
