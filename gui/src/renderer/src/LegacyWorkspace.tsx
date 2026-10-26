import { App } from './App'
import { PmDataProvider } from './lib/pmDataContext'
export default function LegacyWorkspace(): JSX.Element {
  return <PmDataProvider><App /></PmDataProvider>
}
