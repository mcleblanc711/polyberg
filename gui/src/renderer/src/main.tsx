import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { WorkspaceApp } from './WorkspaceApp'
import './styles/global.css'
import './research/research.css'

createRoot(document.getElementById('root')!).render(<StrictMode><WorkspaceApp /></StrictMode>)
