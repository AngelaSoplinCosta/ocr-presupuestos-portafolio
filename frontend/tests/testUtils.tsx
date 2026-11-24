import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode } from 'react'
import { App } from '../src/App'

export function renderAt(path = '/') {
  window.history.pushState({}, '', path)
  return { user: userEvent.setup(), ...render(<App />) }
}

export function renderStrictAt(path = '/') {
  window.history.pushState({}, '', path)
  return { user: userEvent.setup(), ...render(<StrictMode><App /></StrictMode>) }
}

export async function reachReview() {
  const result = renderAt('/')
  const { user } = result
  await user.click(result.getAllByRole('button', { name: 'Probar con un documento de ejemplo' })[0])
  await user.click(result.getByRole('button', { name: 'Mostrar información detectada' }))
  await user.click(result.getByRole('button', { name: 'Continuar a columnas' }))
  await user.click(result.getByRole('button', { name: 'Continuar a revisión' }))
  return result
}

export async function reachColumns() {
  const result = renderAt('/')
  await result.user.click(result.getAllByRole('button', { name: 'Probar con un documento de ejemplo' })[0])
  await result.user.click(result.getByRole('button', { name: 'Mostrar información detectada' }))
  await result.user.click(result.getByRole('button', { name: 'Continuar a columnas' }))
  return result
}
