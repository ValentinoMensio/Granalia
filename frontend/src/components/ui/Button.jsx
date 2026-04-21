function Button({ variant = 'primary', className = '', type = 'button', children, ...props }) {
  const variants = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    ghost: 'btn-ghost',
    danger: 'btn-danger',
  }

  return (
    <button type={type} className={`${variants[variant] || variants.primary} ${className}`.trim()} {...props}>
      {children}
    </button>
  )
}

export default Button
