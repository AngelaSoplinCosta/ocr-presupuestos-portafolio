import { useContext } from 'react'
import { AppContext } from '../context/appContextValue'

export function useApp() {
  const value = useContext(AppContext)
  if (!value) throw new Error('useApp debe utilizarse dentro de AppProvider')
  return value
}
