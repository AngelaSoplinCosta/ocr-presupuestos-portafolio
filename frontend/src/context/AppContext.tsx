import { useReducer, type ReactNode } from 'react'
import { initialColumns } from '../data/demoData'
import { AppContext, type AppAction, type AppState } from './appContextValue'

const baseState: AppState = {
  file: null,
  localJob: null,
  demo: false,
  documentType: 'Presupuesto de obra',
  columns: initialColumns.map((column) => ({ ...column })),
  processingComplete: false,
  columnsConfirmed: false,
  decisions: {},
  templateMessage: '',
  duplicatedTemplates: [],
}

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_FILE':
      return { ...state, file: action.file, localJob: null, demo: false, processingComplete: false, columnsConfirmed: false, columns: initialColumns.map((column) => ({ ...column })), decisions: {} }
    case 'SET_LOCAL_JOB':
      return { ...state, localJob: action.job }
    case 'START_DEMO':
      return { ...baseState, demo: true, columns: initialColumns.map((column) => ({ ...column })) }
    case 'SET_DOCUMENT_TYPE':
      return { ...state, documentType: action.value }
    case 'SET_COLUMNS':
      return { ...state, columns: action.columns.map((column, position) => ({ ...column, position })), columnsConfirmed: false }
    case 'MARK_PROCESSED':
      return { ...state, processingComplete: true, columnsConfirmed: false }
    case 'CONFIRM_COLUMNS':
      return { ...state, columnsConfirmed: true }
    case 'SET_DECISION':
      return { ...state, decisions: { ...state.decisions, [action.observationId]: action.decision } }
    case 'UNDO_DECISION': {
      const decisions = { ...state.decisions }
      delete decisions[action.observationId]
      return { ...state, decisions }
    }
    case 'LOAD_EXAMPLE_DECISIONS':
      return {
        ...state,
        decisions: Object.fromEntries(
          action.observationIds.map((id, index) => [id, { kind: 'suggested', value: action.suggestions[index] }]),
        ),
      }
    case 'SAVE_TEMPLATE_DEMO':
      return { ...state, templateMessage: 'Plantilla guardada para esta demostración' }
    case 'DUPLICATE_TEMPLATE':
      return { ...state, duplicatedTemplates: [...state.duplicatedTemplates, action.name] }
    case 'RESET_PROCESS':
      return { ...baseState, columns: initialColumns.map((column) => ({ ...column })) }
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, baseState)
  return <AppContext.Provider value={{ state, dispatch }}>{children}</AppContext.Provider>
}
