import { emptyItem } from '../../lib/format'

function createInitialForm() {
  return {
    customerId: '',
    clientName: '',
    date: new Date().toISOString().slice(0, 10),
    secondaryLine: '',
    transport: '',
    notes: '',
    footerDiscounts: [],
    lineDiscountsByGroup: {},
    items: [emptyItem()],
  }
}

export { createInitialForm }
