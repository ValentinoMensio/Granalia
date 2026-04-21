import { useState } from 'react'
import Button from '../components/ui/Button'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await login(username, password)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="app-shell flex min-h-screen items-center justify-center py-16">
      <div className="surface w-full max-w-md p-8">
        <div className="mb-6">
          <div className="eyebrow">Acceso protegido</div>
          <h1 className="section-title mt-2 text-3xl">Ingresar al sistema</h1>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="field-label">Usuario</label>
            <input className="input" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </div>
          <div>
            <label className="field-label">Contraseña</label>
            <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" />
          </div>
          {error ? <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}
          <Button type="submit" variant="primary" className="w-full justify-center" disabled={submitting}>
            {submitting ? 'Validando...' : 'Ingresar'}
          </Button>
        </form>
      </div>
    </div>
  )
}
