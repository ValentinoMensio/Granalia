import Panel from '../ui/Panel'
import { API_BASE } from '../../lib/api'
import { money } from '../../lib/format'

function InvoicesPanel({ invoices }) {
  return (
    <Panel title="Facturas">
      <div className="space-y-3 text-sm">
        {invoices.map((invoice) => (
          <a key={invoice.invoice_id} className="block rounded-2xl bg-stone-50 px-4 py-3 transition hover:bg-brand-sand/40" href={`${API_BASE}/api/invoices/${invoice.invoice_id}/xlsx`} target="_blank" rel="noreferrer">
            <div className="font-medium">{invoice.client_name}</div>
            <div className="text-brand-ink/60">{invoice.order_date} · {money(invoice.final_total)}</div>
          </a>
        ))}
      </div>
    </Panel>
  )
}

export default InvoicesPanel
