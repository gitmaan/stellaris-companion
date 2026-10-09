// Keep movement local to the changing control or surface. Page geometry stays fixed.
export const motionTiming = {
  feedback: 0.12,
  content: 0.16,
  surface: 0.2,
} as const

export const motionEase = [0.22, 1, 0.36, 1] as const
