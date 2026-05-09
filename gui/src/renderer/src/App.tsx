import { colors, fonts } from './styles/tokens'

export const App = () => {
  return (
    <>
      <div
        style={{
          height: '100vh',
          width: '100vw',
          background: colors.bg,
          color: colors.text,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div
            style={{
              fontFamily: fonts.display,
              fontWeight: 700,
              fontSize: 32,
              letterSpacing: 0.5,
              color: colors.magenta,
              textShadow: '0 0 14px rgba(255,61,240,0.6)'
            }}
          >
            polyberg / terminal
          </div>
          <div
            style={{
              marginTop: 12,
              fontFamily: fonts.mono,
              fontSize: 10.5,
              letterSpacing: 1.2,
              textTransform: 'uppercase',
              color: colors.textDim
            }}
          >
            v0.1.0 · skeleton
          </div>
        </div>
      </div>
      <div className="scanline-overlay" />
    </>
  )
}
