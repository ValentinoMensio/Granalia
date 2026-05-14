function Metric({ label, value }) {
  return (
    <div className="metric-card">
      <div className="field-label">{label}</div>
      <div className="mt-2 text-2xl font-extrabold tracking-[-0.04em] text-brand-red">{value}</div>
    </div>
  )
}

export default Metric
