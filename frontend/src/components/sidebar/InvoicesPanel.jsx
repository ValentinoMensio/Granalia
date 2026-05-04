import Panel from '../ui/Panel'
import { money } from '../../lib/format'

function shortInvoiceNumber(invoice) {
  if (invoice?.invoice_number) return String(invoice.invoice_number).padStart(8, '0')
  const match = String(invoice?.fiscal_number || '').match(/(\d+)$/)
  if (match) return match[1]
  return `#${invoice?.invoice_id}`
}

function InvoicesPanel({ invoices }) {
  return (
    <Panel title="Facturas">
      <div className="space-y-3 text-sm">
        {invoices.map((invoice) => (
          <div key={invoice.invoice_id} className="block rounded-2xl bg-stone-50 px-4 py-3">
            <div className="font-medium">{shortInvoiceNumber(invoice)} · {invoice.client_name}</div>
            <div className="text-brand-ink/60">{invoice.order_date} · {money(invoice.final_total)}</div>
          </div>
        ))}
      </div>
    </Panel>
  )
}

export default InvoicesPanel
