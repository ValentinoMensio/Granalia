function PageSectionHeader({ eyebrow, title, description, aside }) {
  return (
    <div className="page-header">
      <div>
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h1 className="section-title">{title}</h1>
        {description ? <p className="section-subtitle mt-2 max-w-2xl">{description}</p> : null}
      </div>
      {aside ? <div>{aside}</div> : null}
    </div>
  )
}

export default PageSectionHeader
