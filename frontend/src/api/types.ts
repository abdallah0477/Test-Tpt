// The ONE place where the app names API types (AD-14).
// Everything here is an alias into the generated `schema.d.ts`; nothing is hand-written.
// If a name stops compiling after `npm run gen:types`, fix the alias here, not in the features.
import type { components, paths } from './schema'

type Schemas = components['schemas']

// ---- contract models (names come from contracts/models.py and events.py)
export type Session = Schemas['Session']
export type Inspection = Schemas['Inspection']
export type InspectionStatus = Schemas['InspectionStatus']
export type InspectionCounts = Schemas['InspectionCounts']
export type Finding = Schemas['Finding']
export type BBox = Schemas['BBox']
export type Visibility = Schemas['Visibility']
export type LocatorCandidate = Schemas['LocatorCandidate']
export type Reliability = Schemas['Reliability']
export type Health = Schemas['Health']
export type ModelStatus = Schemas['ModelStatus']
export type ErrorBody = Schemas['ErrorBody']
export type ErrorEnvelope = Schemas['ErrorEnvelope']

// ---- SSE events (discriminated on `event`)
export type SseEvent = Schemas['SseEvent']
export type DoneData = Schemas['DoneData']
export type FailedData = Schemas['FailedData']

// ---- route-specific shapes, taken from the operations so they follow the backend's naming
type Success = 200 | 201 | 202
type JsonOk<Op> = Op extends { responses: infer R }
  ? {
      [K in keyof R & Success]: R[K] extends { content: { 'application/json': infer T } } ? T : never
    }[keyof R & Success]
  : never
type JsonBody<Op> = Op extends { requestBody?: { content: { 'application/json': infer T } } } ? T : never

/** One row of GET /session/{session_id}/inspections. */
export type InspectionSummary = JsonOk<paths['/api/v1/session/{session_id}/inspections']['get']>[number]

/** Body of POST /inspection. */
export type StartInspectionRequest = JsonBody<paths['/api/v1/inspection']['post']>

/** Response of POST /inspection, /inspection/{id}/retry and /inspection/reinspect. */
export type StartedJob = JsonOk<paths['/api/v1/inspection']['post']>

// ---- Epic 2: goal, Scope, filters
export type GoalEntry = Schemas['GoalEntry']
export type FindingRef = Schemas['FindingRef']
export type Scope = Schemas['Scope']

export type ScopeFilters = Schemas['ScopeFilters']
export type GoalRequest = Schemas['GoalRequest']
export type ScopeRequest = Schemas['ScopeRequest']
export type FilterPreviewRequest = Schemas['FilterPreviewRequest']
export type FilterPreview = Schemas['FilterPreview']

// ---- Epic 3: assistant, clarification, usage
export type AssistantJob = Schemas['AssistantJob']
export type AssistantResponse = Schemas['AssistantResponse']
export type ResponseSections = Schemas['ResponseSections']
export type ResponseItem = Schemas['ResponseItem']
export type ClarificationTurn = Schemas['ClarificationTurn']
export type ConfidenceReport = Schemas['ConfidenceReport']
export type ModelCallRecord = Schemas['ModelCallRecord']
export type ResponseUsage = Schemas['ResponseUsage']
export type SessionUsage = Schemas['SessionUsage']
