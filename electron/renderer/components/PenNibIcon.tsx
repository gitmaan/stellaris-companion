interface PenNibIconProps {
  className?: string
}

function PenNibIcon({ className }: PenNibIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M16.24 3.56l4.95 4.94c.78.79.78 2.05 0 2.84L12 20.53a4.008 4.008 0 0 1-2.83 1.17H4v-5.18c0-1.06.42-2.08 1.17-2.83L16.24 3.56zm-.71 1.42L6.59 13.91a2.015 2.015 0 0 0-.59 1.42V19h3.67c.53 0 1.04-.21 1.41-.59l8.95-8.94L15.53 4.98zM14.12 7.1l4.95 4.95-1.41 1.41-4.95-4.95 1.41-1.41z" />
    </svg>
  )
}

export default PenNibIcon
