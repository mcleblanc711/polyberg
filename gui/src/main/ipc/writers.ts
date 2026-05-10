import { readFileSync, writeFileSync } from 'fs'
import { resolve } from 'path'
import yaml from 'js-yaml'
import { assertWritable, CONTEXT_DIR } from './repo'
import type { Catalyst, DraftOrder } from '../../shared/contract'

const CATALYSTS_PATH = resolve(CONTEXT_DIR, 'recent_catalysts.md')
const ORDERS_PATH = resolve(CONTEXT_DIR, 'open_orders.yaml')
const REGISTRY_PATH = resolve(CONTEXT_DIR, 'market_registry.yaml')

const knownMarketIds = (): Set<string> => {
  try {
    const raw = readFileSync(REGISTRY_PATH, 'utf8')
    const parsed = yaml.load(raw) as { markets?: Array<{ market_id?: string }> } | null
    const rows = parsed?.markets ?? []
    return new Set(rows.map((r) => r.market_id).filter((id): id is string => typeof id === 'string'))
  } catch {
    return new Set()
  }
}

const CREDIBLE_HEADING = '## Credible Reporting Watch'

export const appendCatalyst = (marketId: string, entry: Catalyst): void => {
  if (!knownMarketIds().has(marketId)) {
    throw new Error(`Unknown market: ${marketId}`)
  }
  if (typeof entry.t !== 'string' || typeof entry.src !== 'string' || typeof entry.txt !== 'string') {
    throw new Error('Catalyst entry must have t, src, txt strings')
  }
  const path = assertWritable(CATALYSTS_PATH)
  const line = `- [${entry.t}] **${marketId}** · ${entry.src} — ${entry.txt}`
  let body: string
  try {
    body = readFileSync(path, 'utf8')
  } catch {
    body = '# Recent Catalysts\n'
  }
  const headingIdx = body.indexOf(CREDIBLE_HEADING)
  if (headingIdx === -1) {
    const trimmed = body.endsWith('\n') ? body : body + '\n'
    body = `${trimmed}\n${CREDIBLE_HEADING}\n\n${line}\n`
  } else {
    const after = headingIdx + CREDIBLE_HEADING.length
    const nextHeading = body.indexOf('\n## ', after)
    const insertAt = nextHeading === -1 ? body.length : nextHeading
    let prefix = body.slice(0, insertAt).replace(/\s+$/, '')
    prefix += `\n${line}\n`
    body = prefix + body.slice(insertAt)
  }
  writeFileSync(path, body, 'utf8')
}

interface OrdersFile {
  as_of?: string
  buy_orders?: Array<Record<string, unknown>>
  sell_orders?: Array<Record<string, unknown>>
}

export const writeDraftOrder = (order: DraftOrder): void => {
  if (!knownMarketIds().has(order.marketId)) {
    throw new Error(`Unknown market: ${order.marketId}`)
  }
  if (order.side !== 'YES' && order.side !== 'NO') {
    throw new Error(`Invalid side: ${order.side}`)
  }
  if (order.kind !== 'BUY' && order.kind !== 'SELL') {
    throw new Error(`Invalid kind: ${order.kind}`)
  }
  if (!Number.isFinite(order.price) || order.price <= 0 || order.price >= 1) {
    throw new Error(`Price must be in (0, 1): ${order.price}`)
  }
  if (!Number.isFinite(order.shares) || order.shares <= 0) {
    throw new Error(`Shares must be > 0: ${order.shares}`)
  }
  const path = assertWritable(ORDERS_PATH)
  let parsed: OrdersFile
  try {
    parsed = (yaml.load(readFileSync(path, 'utf8')) as OrdersFile | null) ?? {}
  } catch {
    parsed = {}
  }
  const entry: Record<string, unknown> = {
    market_id: order.marketId,
    side: order.side,
    price: order.price,
    shares: order.shares,
    order_type: 'limit'
  }
  if (order.notes) entry.notes = order.notes
  const list = order.kind === 'BUY' ? 'buy_orders' : 'sell_orders'
  const existing = parsed[list] ?? []
  parsed[list] = [...existing, entry]
  parsed.as_of = new Date().toISOString()
  writeFileSync(path, yaml.dump(parsed, { lineWidth: 120, quotingType: '"' }), 'utf8')
}
