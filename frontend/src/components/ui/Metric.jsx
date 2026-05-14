function Metric({ label, value }) {
  return (
    <div className="metric-card">
      <div className="field-label">{label}</div>
      <div className="amount-text mt-2 text-2xl tracking-[-0.04em]">{value}</div>
    </div>
  )
}

export default Metric
