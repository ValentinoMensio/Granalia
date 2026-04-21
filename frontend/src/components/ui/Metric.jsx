function Metric({ label, value }) {
  return (
    <div className="metric-card">
      <div className="field-label">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-brand-red">{value}</div>
    </div>
  )
}

export default Metric
