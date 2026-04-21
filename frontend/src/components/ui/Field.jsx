function Field({ label, full, children }) {
  return (
    <label className={full ? 'md:col-span-2' : ''}>
      <span className="field-label">{label}</span>
      {children}
    </label>
  )
}

export default Field
