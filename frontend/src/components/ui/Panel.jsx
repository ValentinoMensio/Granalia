function Panel({ title, children }) {
  return (
    <section className="surface p-4 sm:p-6">
      <h3 className="subsection-title mb-4">{title}</h3>
      {children}
    </section>
  )
}

export default Panel
