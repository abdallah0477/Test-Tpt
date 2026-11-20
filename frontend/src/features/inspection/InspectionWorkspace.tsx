import { useState, type ReactNode } from 'react'
import type { Inspection } from '../../api/types'
import { inspectionUrls } from '../../api/inspection'
import { AssistantPanel } from '../assistant/AssistantPanel'
import { FindingLinks } from '../assistant/findingLinks'
import { FilterBar } from '../session/FilterBar'
import { GoalEditor } from '../session/GoalEditor'
import { assignScopeColors } from '../session/scopeColors'
import { onlyRecorded, removeId, scopeBelongsElsewhere, scopeIdsFor, toggleId } from '../session/scopeOps'
import { ScopePanel } from '../session/ScopePanel'
import type { SessionEditing } from '../session/useSessionEditing'
import { FindingDetail } from './FindingDetail'
import { FindingsTable } from './FindingsTable'
import { ScreenshotView } from './ScreenshotView'
import { StatusBanner } from './StatusBanner'

interface InspectionWorkspaceProps {
  inspection: Inspection
  busy: boolean
  onRetry: () => void
  onReinspect: () => void
  /** Goal / Scope / filter editing for the Session (Epic 2). */
  editing: SessionEditing
  /** Extra content for the side panel, below the Finding detail (e.g. history). */
  side?: ReactNode
}

/**
 * Results of one Inspection: status, goal, filters, screenshot + Findings table in the main
 * area; Scope and Finding detail in the side panel. Render it with `key={inspection_id}` so
 * the active Finding resets when another Inspection is opened.
 */
export function InspectionWorkspace({ inspection, busy, onRetry, onReinspect, editing, side }: InspectionWorkspaceProps) {
  const [activeId, setActiveId] = useState<string | null>(null)
  const inspectionId = inspection.inspection_id
  const findings = inspection.findings ?? []
  const index = findings.findIndex((f) => f.finding_id === activeId)
  const active = index >= 0 ? findings[index] : null

  const { session } = editing
  const scopeIds = onlyRecorded(scopeIdsFor(session, inspectionId), findings)
  const scopeColors = assignScopeColors(scopeIds)
  const canEdit = !!session && !editing.saving
  const setScope = (ids: string[]) => editing.setScope(inspectionId, onlyRecorded(ids, findings))

  return (
    <FindingLinks.Provider value={{ inspectionId, findings, openFinding: setActiveId }}>
      <section className="area-main" aria-label="Inspection results">
        <div className="inspection-head">
          <div>
            <p className="inspection-url">
              <strong>{inspection.requested_url}</strong>
              {inspection.final_url && inspection.final_url !== inspection.requested_url && <> → {inspection.final_url}</>}
            </p>
            <p className="muted">
              {inspectionId} · captured {new Date(inspection.captured_at).toLocaleString()}
            </p>
          </div>
          <div className="toolbar">
            <button type="button" className="btn" onClick={onReinspect} disabled={busy}>
              Re-inspect
            </button>
            <a className="btn" href={inspectionUrls.export(inspectionId)} download>
              Export JSON
            </a>
          </div>
        </div>

        <StatusBanner inspection={inspection} busy={busy} onRetry={onRetry} onReinspect={onReinspect} />

        {editing.message && (
          <p className="field-error" role="alert">
            {editing.message}
          </p>
        )}

        <GoalEditor goals={session?.goals ?? []} saving={editing.saving} disabled={!session} onSave={editing.saveGoal} />

        {findings.length > 0 && (
          <FilterBar
            // Re-initialise from the stored filters once the Session has loaded.
            key={`${inspectionId}-${session ? 'loaded' : 'loading'}`}
            findings={findings}
            initial={session?.filters}
            saving={!canEdit}
            onApply={(filters, ids) => editing.applyFilters(inspectionId, filters, onlyRecorded(ids, findings))}
          />
        )}

        {scopeBelongsElsewhere(session, inspectionId) && (
          <p className="notice" role="note">
            The current Scope belongs to inspection {session?.scope?.inspection_id}. Selecting here starts a new Scope for this
            inspection.
          </p>
        )}

        <div className="results">
          <ScreenshotView
            src={inspection.screenshot ? inspectionUrls.screenshot(inspectionId) : null}
            findings={findings}
            activeId={activeId}
            onSelect={setActiveId}
            scopeColors={scopeColors}
          />
          <div className="table-scroll">
            <p className="scope-counter" role="status">
              {scopeIds.length} {scopeIds.length === 1 ? 'element' : 'elements'} selected
            </p>
            <FindingsTable
              findings={findings}
              activeId={activeId}
              onSelect={setActiveId}
              scopeColors={scopeColors}
              onToggleScope={(id) => setScope(toggleId(scopeIds, id))}
              scopeDisabled={!canEdit}
            />
            <p className="muted table-hint">Tick “Scope” to add or remove a Finding; click its name to see its details.</p>
          </div>
        </div>

        <AssistantPanel editing={editing} />
      </section>

      <aside className="area-side" aria-label="Details">
        <ScopePanel
          findings={findings}
          scopeIds={scopeIds}
          colors={scopeColors}
          saving={!canEdit}
          onRemove={(id) => setScope(removeId(scopeIds, id))}
          onClear={() => setScope([])}
          onShow={setActiveId}
        />
        {active ? (
          <FindingDetail inspectionId={inspectionId} finding={active} number={index + 1} sessionId={session?.session_id ?? null} />
        ) : (
          <p className="empty-note">Click a Finding's name in the table, or its marker, to see its details.</p>
        )}
        {side}
      </aside>
    </FindingLinks.Provider>
  )
}
