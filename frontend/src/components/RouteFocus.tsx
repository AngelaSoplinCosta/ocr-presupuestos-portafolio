import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

export function RouteFocus() {
  const location = useLocation()
  useEffect(() => {
    document.documentElement.lang = 'es'
    const title = document.querySelector<HTMLElement>('[data-page-title]')
    title?.focus()
  }, [location.pathname])
  return null
}
