/** Shared Semantic Layer table pagination and scroll sizing. */

export const SEMANTIC_DEFAULT_PAGE_SIZE = 5

/** Backend list endpoints cap page_size at 200. */
export const SEMANTIC_API_MAX_PAGE_SIZE = 200

export const SEMANTIC_PAGE_SIZE_OPTIONS = [5, 10, 20] as const

/** Max height for scrollable table body (~56px per row + header clearance). */
export function semanticTableBodyMaxHeightClass(pageSize: number): string {
  if (pageSize <= 5) return 'max-h-[20rem]'
  if (pageSize <= 10) return 'max-h-[32rem]'
  return 'max-h-[38rem]'
}
