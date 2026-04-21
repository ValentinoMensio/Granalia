import Panel from '../ui/Panel'

function TransportPanel({ transports }) {
  return (
    <Panel title="Transportes">
      <div className="space-y-2 text-sm">
        {transports.slice(0, 8).map((transport) => (
          <div key={transport.transport_id} className="rounded-2xl bg-stone-50 px-4 py-3">{transport.name}</div>
        ))}
      </div>
    </Panel>
  )
}

export default TransportPanel
