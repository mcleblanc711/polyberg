import { readFileSync, statSync } from 'fs'
import { resolve } from 'path'
import type { ArtifactName, ArtifactRead } from '../../shared/contract'
import { ageMinutes, assertReadable, REPORTS_DIR } from './repo'

const FILENAMES: Record<ArtifactName, string> = {
  packet: 'packet.md',
  'adjudicator-input': 'adjudicator_input.md'
}

export const readArtifact = (name: ArtifactName): ArtifactRead => {
  const filename = FILENAMES[name]
  const abs = assertReadable(resolve(REPORTS_DIR, filename))
  const empty: ArtifactRead = {
    name,
    filename,
    exists: false,
    content: '',
    bytes: 0,
    mtimeIso: '',
    ageMin: null
  }
  try {
    const content = readFileSync(abs, 'utf8')
    const stat = statSync(abs)
    return {
      name,
      filename,
      exists: true,
      content,
      bytes: stat.size,
      mtimeIso: new Date(stat.mtimeMs).toISOString(),
      ageMin: ageMinutes(abs)
    }
  } catch {
    return empty
  }
}
