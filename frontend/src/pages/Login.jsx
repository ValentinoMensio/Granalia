import { useState } from 'react'
import Button from '../components/ui/Button'
import { useAuth } from '../context/AuthContext'
import logoImage from '../../../img/logof.png'

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
    <div className="app-shell flex min-h-screen items-center justify-center py-6 sm:py-16">
      <div className="grid w-full max-w-5xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-card lg:grid-cols-[1fr_420px]">
        <div className="hidden bg-slate-950 p-10 text-white lg:flex lg:flex-col lg:justify-between">
          <div>
            <img src={logoImage} alt="Granalia" className="h-20 w-auto object-contain" />
            <h1 className="mt-8 text-4xl font-extrabold tracking-[-0.05em]">Facturación simple para operación diaria.</h1>
            <p className="mt-4 max-w-sm text-sm leading-6 text-white/62">Clientes, transportes, productos, historial y emisión en una interfaz pensada para velocidad y control.</p>
          </div>
          <div className="grid grid-cols-3 gap-3 text-xs text-white/60">
            <div className="rounded-2xl border border-white/10 p-3">PDF</div>
            <div className="rounded-2xl border border-white/10 p-3">XLSX</div>
            <div className="rounded-2xl border border-white/10 p-3">PostgreSQL</div>
          </div>
        </div>

        <div className="p-5 sm:p-8 lg:p-10">
          <img src={logoImage} alt="Granalia" className="mb-6 h-16 w-auto object-contain lg:hidden" />
          <div className="mb-8">
            <div className="eyebrow">Acceso protegido</div>
            <h1 className="section-title mt-2 text-3xl">Ingresar</h1>
            <p className="section-subtitle mt-2">Usá tus credenciales para continuar.</p>
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
            {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}
            <Button type="submit" variant="primary" className="w-full justify-center" disabled={submitting}>
              {submitting ? 'Validando...' : 'Ingresar'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
