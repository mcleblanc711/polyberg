import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { PmDataProvider } from './lib/pmDataContext'
import './styles/global.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PmDataProvider>
      <App />
    </PmDataProvider>
  </StrictMode>
)
