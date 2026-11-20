// Colour pairing for Findings in Scope (Story 2.2, FR-11).
// A fixed palette of distinguishable, high-contrast colours (Okabe-Ito based, colour-blind friendly).
// Unselected markers use a grey dashed outline, so they never look like a selected colour.
// Beyond the palette size colours are reused; the Finding number is always shown with the colour.

export interface ScopeColor {
  /** Outline / swatch colour. */
  color: string
  /** Text colour readable on `color` (>= 4.5:1). */
  text: string
}

export const SCOPE_PALETTE: readonly ScopeColor[] = [
  { color: '#0072B2', text: '#ffffff' }, // blue
  { color: '#E69F00', text: '#000000' }, // orange
  { color: '#009E73', text: '#000000' }, // bluish green
  { color: '#D55E00', text: '#000000' }, // vermillion
  { color: '#CC79A7', text: '#000000' }, // reddish purple
  { color: '#56B4E9', text: '#000000' }, // sky blue
  { color: '#F0E442', text: '#000000' }, // yellow
  { color: '#6A3D9A', text: '#ffffff' }, // purple
  { color: '#8C510A', text: '#ffffff' }, // brown
  { color: '#1B7837', text: '#ffffff' }, // dark green
]

export interface ScopeColorAssignment extends ScopeColor {
  /** 0-based position in the Scope. */
  position: number
  /** True when another Finding in the Scope has the same colour (palette exhausted). */
  reused: boolean
}

/** Colours by Scope order: the n-th selected Finding gets palette[n % size]. */
export function assignScopeColors(findingIds: string[]): Map<string, ScopeColorAssignment> {
  const size = SCOPE_PALETTE.length
  const many = findingIds.length > size
  return new Map(
    findingIds.map((id, position) => {
      const slot = position % size
      // Every Finding sharing a slot is "reused", including the first one.
      const reused = many && (position >= size || slot < findingIds.length - size)
      return [id, { ...SCOPE_PALETTE[slot], position, reused }]
    }),
  )
}
