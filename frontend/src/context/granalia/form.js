import { emptyItem } from '../../lib/format'

function createInitialForm() {
  return {
    customerId: '',
    priceListId: '',
    declared: false,
    clientName: '',
    date: new Date().toISOString().slice(0, 10),
    secondaryLine: '',
    transport: '',
    notes: '',
    footerDiscounts: [],
    lineDiscountsByGroup: {},
    automaticBonusRules: [],
    automaticBonusDisablesLineDiscount: false,
    items: [emptyItem()],
  }
}

export { createInitialForm }
