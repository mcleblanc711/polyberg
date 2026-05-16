export const colors = {
  bg: '#030004',
  bgPanel: '#070005',
  bgRaise: '#0e0009',
  bgRow: '#060004',
  bgInput: '#08000c',
  line: '#2a0928',
  line2: '#1a0512',
  lineHot: 'rgba(255,61,240,0.45)',
  text: '#f0e8f5',
  textDim: '#a08aa0',
  textMute: '#7a5e7a',
  cyanText: '#5cf3d3',
  magenta: '#ff3df0',
  magentaSft: 'rgba(255,61,240,0.14)',
  magentaDim: 'rgba(255,61,240,0.06)',
  cyan: '#00ffd1',
  cyanSft: 'rgba(0,255,209,0.12)',
  amber: '#ffb420',
  amberSft: 'rgba(255,180,32,0.14)',
  red: '#ff3d6b',
  redSft: 'rgba(255,61,107,0.14)',
  yes: '#00ffd1',
  no: '#ff3d6b'
} as const

export const fonts = {
  display: '"Space Grotesk", system-ui, sans-serif',
  body: '"Inter", system-ui, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, monospace'
} as const

export const clipCard =
  'polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))'
