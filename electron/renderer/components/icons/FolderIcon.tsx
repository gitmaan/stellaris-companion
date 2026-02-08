import React from 'react'

interface IconProps {
  className?: string
  size?: number
}

/**
 * Style A: Simple folder outline
 * Clean, minimal, matches HUD aesthetic
 */
export const FolderIconA: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Folder body */}
    <path
      d="M6 14V38C6 39.1046 6.89543 40 8 40H40C41.1046 40 42 39.1046 42 38V18C42 16.8954 41.1046 16 40 16H24L20 10H8C6.89543 10 6 10.8954 6 12V14Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
  </svg>
)

/**
 * Style B: Folder with tab detail
 * Slightly more elaborate, still clean
 */
export const FolderIconB: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Folder back/tab */}
    <path
      d="M8 12H19L23 16"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    {/* Folder body */}
    <rect
      x="6"
      y="16"
      width="36"
      height="24"
      rx="2"
      stroke="currentColor"
      strokeWidth="1.5"
    />
  </svg>
)

/**
 * Style C: Filing cabinet drawer
 * More "filing cabinet" literal interpretation
 */
export const FolderIconC: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Cabinet body */}
    <rect
      x="8"
      y="6"
      width="32"
      height="36"
      rx="2"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    {/* Drawer divider lines */}
    <line x1="8" y1="18" x2="40" y2="18" stroke="currentColor" strokeWidth="1.5" />
    <line x1="8" y1="30" x2="40" y2="30" stroke="currentColor" strokeWidth="1.5" />
    {/* Drawer handles */}
    <line x1="20" y1="12" x2="28" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="20" y1="24" x2="28" y2="24" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <line x1="20" y1="36" x2="28" y2="36" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
)

/**
 * Style D: Open folder with document
 * Suggests "your file is open"
 */
export const FolderIconD: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Document peeking out */}
    <rect
      x="14"
      y="8"
      width="20"
      height="26"
      rx="1"
      stroke="currentColor"
      strokeWidth="1.5"
      opacity="0.5"
    />
    {/* Document lines */}
    <line x1="18" y1="14" x2="30" y2="14" stroke="currentColor" strokeWidth="1" opacity="0.5" />
    <line x1="18" y1="18" x2="28" y2="18" stroke="currentColor" strokeWidth="1" opacity="0.5" />
    <line x1="18" y1="22" x2="26" y2="22" stroke="currentColor" strokeWidth="1" opacity="0.5" />
    {/* Folder body */}
    <path
      d="M6 20V38C6 39.1046 6.89543 40 8 40H40C41.1046 40 42 39.1046 42 38V24C42 22.8954 41.1046 22 40 22H26L22 18H8C6.89543 18 6 18.8954 6 20Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
  </svg>
)

/**
 * Style E: Geometric folder with inner accent line
 * Bold inner line so it reads as intentional
 */
export const FolderIconE: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Outer folder shape */}
    <path
      d="M6 16L6 38L42 38L42 20L26 20L22 14L6 14L6 16Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    {/* Inner accent line - bolder */}
    <path
      d="M10 24H38"
      stroke="currentColor"
      strokeWidth="1.5"
      opacity="0.7"
    />
  </svg>
)

/**
 * Style F: Folder with corner bracket accents
 * Bolder brackets so they're clearly intentional
 */
export const FolderIconF: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    {/* Corner accents - top left */}
    <path d="M2 14H8V8" stroke="currentColor" strokeWidth="1.5" opacity="0.8" />
    {/* Corner accents - bottom right */}
    <path d="M46 34H40V40" stroke="currentColor" strokeWidth="1.5" opacity="0.8" />
    {/* Main folder shape */}
    <path
      d="M8 16V36H40V20H25L21 14H8V16Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
  </svg>
)

/**
 * Style G: Geometric folder - thicker stroke
 * Clean shape with bolder line weight for presence
 */
export const FolderIconG: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <path
      d="M6 16L6 38L42 38L42 20L26 20L22 14L6 14L6 16Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinejoin="round"
    />
  </svg>
)

/**
 * Style H: Filled folder with inner line
 * Subtle fill + accent line
 */
export const FolderIconH: React.FC<IconProps> = ({ className = '', size = 48 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className={className}
  >
    <path
      d="M6 16L6 38L42 38L42 20L26 20L22 14L6 14L6 16Z"
      fill="currentColor"
      fillOpacity="0.1"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    {/* Inner accent line */}
    <path
      d="M10 24H38"
      stroke="currentColor"
      strokeWidth="1.5"
      opacity="0.5"
    />
  </svg>
)

// Default export - choose your preferred style
export default FolderIconE
