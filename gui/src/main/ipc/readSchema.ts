import { readFileSync } from 'fs'
import { resolve } from 'path'
import type { SchemaName } from '../../shared/contract'
import { assertReadable, SCHEMAS_DIR } from './repo'

const FILENAMES: Record<SchemaName, string> = {
  'model-trade-response': 'model_trade_response.schema.json',
  'adjudicator-output': 'adjudicator_output.schema.json'
}

// Return the raw schema JSON text so the renderer can embed it verbatim in a
// format-forcing prompt. Reading from disk keeps the schemas/ files the single
// source of truth — the same files the validate stages check pasted JSON against.
export const readSchema = (name: SchemaName): string => {
  const filename = FILENAMES[name]
  if (!filename) {
    throw new Error(`Unknown schema: ${name}`)
  }
  const abs = assertReadable(resolve(SCHEMAS_DIR, filename))
  return readFileSync(abs, 'utf8')
}
