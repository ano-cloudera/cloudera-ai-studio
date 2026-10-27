import type { ConnectorType } from '../../types/api'

const ICON_BY_TYPE: Partial<Record<ConnectorType, { src: string; kind: 'svg' | 'raster' }>> = {
  postgres: { src: '/icons/datasources/postgres.png', kind: 'raster' },
  impala: { src: '/icons/datasources/impala.svg', kind: 'svg' },
  trino: { src: '/icons/datasources/trino.jpg', kind: 'raster' },
}

type Props = {
  connectorType: ConnectorType | string
  size?: number
  className?: string
}

export function ConnectorTypeIcon({ connectorType, size = 20, className = '' }: Props) {
  const key = String(connectorType).toLowerCase() as ConnectorType
  const entry = ICON_BY_TYPE[key]
  if (!entry) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center rounded-md bg-slate-100 text-[10px] font-bold text-slate-500 ${className}`}
        style={{ width: size, height: size }}
        aria-hidden
      >
        DB
      </span>
    )
  }

  if (entry.kind === 'svg') {
    // Official Impala mark is tall; preserve aspect so it fills the tile vertically.
    const height = size
    const width = Math.max(8, Math.round((34.476727 / 81.704071) * height))
    return (
      <img
        src={entry.src}
        alt=""
        width={width}
        height={height}
        className={`inline-block shrink-0 object-contain ${className}`}
        style={{ width, height }}
        draggable={false}
      />
    )
  }

  return (
    <img
      src={entry.src}
      alt=""
      width={size}
      height={size}
      className={`inline-block shrink-0 rounded-sm object-contain ${className}`}
      draggable={false}
    />
  )
}
