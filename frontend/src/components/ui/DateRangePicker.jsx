import { useEffect, useMemo, useRef, useState } from 'react'

const WEEKDAYS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']
const MONTHS = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

function dateKey(date) {
  return date.toLocaleDateString('en-CA')
}

function parseDate(value) {
  if (!value) return null
  const [year, month, day] = String(value).split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day)
}

function formatLabel(value) {
  if (!value) return ''
  const [year, month, day] = String(value).split('-')
  return `${day}/${month}/${year}`
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

function addMonths(date, amount) {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1)
}

function calendarDays(monthDate) {
  const first = startOfMonth(monthDate)
  const firstDay = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - firstDay)

  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(start)
    day.setDate(start.getDate() + index)
    return day
  })
}

function DateRangePicker({ dateFrom = '', dateTo = '', onChange, placeholder = 'Fecha inicio - fecha fin' }) {
  const wrapperRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [selectingEnd, setSelectingEnd] = useState(false)
  const [hoverDate, setHoverDate] = useState('')
  const [visibleMonth, setVisibleMonth] = useState(startOfMonth(parseDate(dateFrom) || new Date()))
  const days = useMemo(() => calendarDays(visibleMonth), [visibleMonth])
  const rangeStart = dateFrom
  const rangeEnd = selectingEnd ? hoverDate : dateTo
  const minRange = rangeStart && rangeEnd ? (rangeStart < rangeEnd ? rangeStart : rangeEnd) : ''
  const maxRange = rangeStart && rangeEnd ? (rangeStart < rangeEnd ? rangeEnd : rangeStart) : ''
  const label = dateFrom && dateTo ? `${formatLabel(dateFrom)} - ${formatLabel(dateTo)}` : dateFrom ? `${formatLabel(dateFrom)} - ...` : ''

  useEffect(() => {
    function handlePointerDown(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [])

  function commitDay(nextDate) {
    if (!selectingEnd || !dateFrom) {
      onChange({ dateFrom: nextDate, dateTo: '' })
      setSelectingEnd(true)
      setHoverDate('')
      return
    }

    const nextFrom = dateFrom <= nextDate ? dateFrom : nextDate
    const nextTo = dateFrom <= nextDate ? nextDate : dateFrom
    onChange({ dateFrom: nextFrom, dateTo: nextTo })
    setSelectingEnd(false)
    setHoverDate('')
    setOpen(false)
  }

  function clearRange(event) {
    event.stopPropagation()
    onChange({ dateFrom: '', dateTo: '' })
    setSelectingEnd(false)
    setHoverDate('')
  }

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        className="input flex min-h-[42px] w-full items-center justify-between gap-2 text-left"
        onClick={() => setOpen((current) => !current)}
      >
        <span className={label ? 'text-slate-800' : 'text-slate-400'}>{label || placeholder}</span>
        {dateFrom || dateTo ? (
          <span className="text-xs font-semibold text-slate-400 hover:text-brand-red" onClick={clearRange}>Limpiar</span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute left-0 z-30 mt-2 w-[19rem] rounded-3xl border border-stone-200 bg-white p-4 shadow-2xl shadow-slate-900/12">
          <div className="mb-3 flex items-center justify-between gap-2">
            <button type="button" className="btn-ghost px-2 py-1" onClick={() => setVisibleMonth((current) => addMonths(current, -1))}>‹</button>
            <div className="text-sm font-bold text-brand-ink">{MONTHS[visibleMonth.getMonth()]} {visibleMonth.getFullYear()}</div>
            <button type="button" className="btn-ghost px-2 py-1" onClick={() => setVisibleMonth((current) => addMonths(current, 1))}>›</button>
          </div>

          <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-bold uppercase tracking-[0.12em] text-slate-400">
            {WEEKDAYS.map((weekday, index) => <div key={`${weekday}-${index}`}>{weekday}</div>)}
          </div>

          <div className="mt-2 grid grid-cols-7 gap-1">
            {days.map((day) => {
              const key = dateKey(day)
              const isOutside = day.getMonth() !== visibleMonth.getMonth()
              const isStart = key === dateFrom
              const isEnd = key === dateTo
              const inRange = minRange && maxRange && key >= minRange && key <= maxRange
              const isToday = key === dateKey(new Date())
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => commitDay(key)}
                  onMouseEnter={() => selectingEnd && setHoverDate(key)}
                  className={`h-9 rounded-xl text-sm transition ${isOutside ? 'text-slate-300' : 'text-slate-700'} ${inRange ? 'bg-brand-sand/70' : 'hover:bg-stone-100'} ${isStart || isEnd ? 'bg-brand-red text-white hover:bg-brand-red' : ''} ${isToday && !isStart && !isEnd ? 'ring-1 ring-brand-red/40' : ''}`}
                >
                  {day.getDate()}
                </button>
              )
            })}
          </div>

          <div className="mt-3 text-xs text-slate-500">
            {selectingEnd ? 'Elegí la fecha de fin.' : 'Elegí la fecha de inicio.'}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default DateRangePicker
