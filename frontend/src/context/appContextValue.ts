import { createContext, type Dispatch } from 'react'
import type { ColumnDefinition, Decision, DocumentType, Job } from '../types'

export interface AppState {
  file: File | null
  localJob: Job | null
  demo: boolean
  documentType: DocumentType
  columns: ColumnDefinition[]
  processingComplete: boolean
  columnsConfirmed: boolean
  decisions: Record<string, Decision>
  templateMessage: string
  duplicatedTemplates: string[]
}

export type AppAction =
  | { type: 'SET_FILE'; file: File | null }
  | { type: 'SET_LOCAL_JOB'; job: Job }
  | { type: 'START_DEMO' }
  | { type: 'SET_DOCUMENT_TYPE'; value: DocumentType }
  | { type: 'SET_COLUMNS'; columns: ColumnDefinition[] }
  | { type: 'MARK_PROCESSED' }
  | { type: 'CONFIRM_COLUMNS' }
  | { type: 'SET_DECISION'; observationId: string; decision: Decision }
  | { type: 'UNDO_DECISION'; observationId: string }
  | { type: 'LOAD_EXAMPLE_DECISIONS'; observationIds: string[]; suggestions: string[] }
  | { type: 'SAVE_TEMPLATE_DEMO' }
  | { type: 'DUPLICATE_TEMPLATE'; name: string }
  | { type: 'RESET_PROCESS' }

export const AppContext = createContext<{ state: AppState; dispatch: Dispatch<AppAction> } | null>(null)
