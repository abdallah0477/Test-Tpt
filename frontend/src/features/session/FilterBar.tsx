import { useState } from 'react'
import type { Finding } from '../../api/types'
import { applyFilters, hasActiveFilters, NO_FILTERS, observedOptions, withDefaults, type FilterInput, type FullFilters } from './scopeFilter'

interface FilterBarProps {
  findings: Finding[]
  /** Filters stored in the Session; used as the starting values. */
  initial: FilterInput | null | undefined
  saving: boolean
  /** Store the filters and replace the Scope with the matching Finding ids. */
  onApply: (filters: FullFilters, matchingIds: string[]) => void
}

/** A single-choice select over observed values; "" means "any". Stored as a 0/1-item list. */
function ListSelect(props: { id: string; label: string; anyLabel: string; options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="filter-field">
      <label htmlFor={props.id}>{props.label}</label>
      <select id={props.id} value={props.value[0] ?? ''} onChange={(e) => props.onChange(e.target.value ? [e.target.value] : [])}>
        <option value="">{props.anyLabel}</option>
        {props.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  )
}

/** Combinable group filters with a live count (Story 2.3). Options come only from recorded Findings. */
export function FilterBar({ findings, initial, saving, onApply }: FilterBarProps) {
  const [filters, setFilters] = useState<FullFilters>(() => withDefaults(initial))
  const options = observedOptions(findings)
  const matching = applyFilters(findings, filters)
  const set = <K extends keyof FullFilters>(key: K, value: FullFilters[K]) => setFilters((f) => ({ ...f, [key]: value }))

  return (
    <section className="filter-bar" aria-labelledby="filter-title">
      <h2 id="filter-title" className="section-title">
        Filters <span className="muted">(all combined with AND)</span>
      </h2>
      <div className="filter-fields">
        <div className="filter-field">
          <label htmlFor="filter-container">Container</label>
          <select id="filter-container" value={filters.container ?? ''} onChange={(e) => set('container', e.target.value || null)}>
            <option value="">Any container</option>
            {options.containers.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <ListSelect id="filter-type" label="Element type" anyLabel="Any type" options={options.kinds} value={filters.element_types} onChange={(v) => set('element_types', v)} />
        <ListSelect id="filter-role" label="Role" anyLabel="Any role" options={options.roles} value={filters.roles} onChange={(v) => set('roles', v)} />
        <ListSelect id="filter-exclude-type" label="Exclude type" anyLabel="Exclude nothing" options={options.kinds} value={filters.exclude_types} onChange={(v) => set('exclude_types', v)} />
        <ListSelect id="filter-exclude-role" label="Exclude role" anyLabel="Exclude nothing" options={options.roles} value={filters.exclude_roles} onChange={(v) => set('exclude_roles', v)} />
        <div className="filter-field filter-checks">
          <label>
            <input type="checkbox" checked={filters.include_hidden} onChange={(e) => set('include_hidden', e.target.checked)} /> Include hidden
          </label>
          <label>
            <input type="checkbox" checked={filters.only_clickable} onChange={(e) => set('only_clickable', e.target.checked)} /> Only clickable
          </label>
        </div>
      </div>
      <div className="filter-actions">
        <span className="filter-count" role="status" aria-live="polite">
          {matching.length} of {findings.length} Findings match
        </span>
        <button
          type="button"
          className="btn btn-primary"
          disabled={saving || matching.length === 0}
          onClick={() => onApply(filters, matching.map((f) => f.finding_id))}
        >
          Apply to Scope
        </button>
        <button type="button" className="btn" disabled={!hasActiveFilters(filters)} onClick={() => setFilters(NO_FILTERS)}>
          Reset filters
        </button>
      </div>
    </section>
  )
}
