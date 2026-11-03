/** "fulfillment_delivery" is shown as "Fulfillment Delivery"; a name someone already wrote with spaces is left alone. */
export function displayModelName(name: string): string {
  if (!/[_-]/.test(name) || /\s/.test(name)) return name
  return name
    .split(/[_-]+/)
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

const letters = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, '')

/** The key is shown next to a name only when it says something the name does not. */
export function showKey(model: { name: string; key: string }): boolean {
  return letters(model.key) !== letters(model.name)
}

/** What will be lost when a draft that was never published is discarded. */
export function discardDraftMessage(
  draftNumber: number,
  published: { versionNumber: number } | null,
  counts?: { entities: number; metrics: number; dimensions: number } | null,
): string {
  if (published) {
    return [`Delete draft v${draftNumber} and return to published v${published.versionNumber}.`, 'Unsaved editor changes will be lost. This cannot be undone.'].join('\n')
  }
  const lost = counts ? `${counts.entities} data models, ${counts.metrics} metrics and ${counts.dimensions} dimensions` : 'all its data models, metrics and dimensions'
  return [
    `This model has never been published, so discarding draft v${draftNumber} deletes everything you built: ${lost}.`,
    'The model stays in the list, but empty. This cannot be undone.',
  ].join('\n')
}
