import { useGranalia } from '../../context/GranaliaContext'

function StatusBar() {
  const { status } = useGranalia()
  return (
    <div className="status-bar">
      {status || 'Listo.'}
    </div>
  )
}

export default StatusBar
