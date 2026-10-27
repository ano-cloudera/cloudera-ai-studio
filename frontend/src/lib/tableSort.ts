/** Toggle sort: first activation on a column → DESC; same column → flip ASC/DESC. */
export function nextSortState(
  currentField: string,
  currentOrder: 'asc' | 'desc',
  clickedField: string,
): { field: string; order: 'asc' | 'desc' } {
  if (currentField !== clickedField) {
    return { field: clickedField, order: 'desc' }
  }
  return { field: clickedField, order: currentOrder === 'desc' ? 'asc' : 'desc' }
}
