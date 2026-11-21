// Small stroke icons used instead of text glyphs. Decorative: always paired with text.
export type IconName = 'check' | 'cross' | 'alert' | 'clock' | 'lock' | 'partial' | 'dot' | 'ring' | 'download' | 'refresh' | 'external'

const PATHS: Record<IconName, string> = {
  check: 'M4 10.5l4 4 8-9',
  cross: 'M5 5l10 10M15 5L5 15',
  alert: 'M10 3l8 14H2L10 3zM10 8v4M10 14.5v.5',
  clock: 'M10 3a7 7 0 100 14 7 7 0 000-14zM10 6v4l3 2',
  lock: 'M5 9h10v8H5zM7 9V6.5a3 3 0 016 0V9',
  partial: 'M10 3a7 7 0 100 14 7 7 0 000-14zM10 3v14',
  dot: 'M10 6a4 4 0 100 8 4 4 0 000-8z',
  ring: 'M10 5a5 5 0 100 10 5 5 0 000-10z',
  download: 'M10 3v10M5.5 9l4.5 4.5L14.5 9M4 17h12',
  refresh: 'M16 10a6 6 0 11-1.8-4.3M16 3.5v3.7h-3.7',
  external: 'M11 4h5v5M16 4l-7 7M14 12v4H4V6h4',
}

export function Icon({ name, className }: { name: IconName; className?: string }) {
  const filled = name === 'dot'
  return (
    <svg
      className={`icon${className ? ` ${className}` : ''}`}
      viewBox="0 0 20 20"
      width="1em"
      height="1em"
      aria-hidden="true"
      focusable="false"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={filled ? 0 : 1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  )
}

/** The Test-TPT mark: an element framed by inspection corner brackets. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" width={size} height={size} aria-hidden="true" focusable="false">
      <path d="M3 10V3h7M22 3h7v7M29 22v7h-7M10 29H3v-7" fill="none" stroke="var(--signal)" strokeWidth="2.6" strokeLinecap="square" />
      <rect x="9" y="12" width="14" height="8" rx="1.5" fill="currentColor" />
    </svg>
  )
}
