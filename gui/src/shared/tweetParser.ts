// Tweet intake auto-parser.
//
// Turns a raw paste copied from the X (Twitter) web UI into the fields the
// Intake screen needs: the author handle and the tweet body, with the
// metadata and trailing "Source:" line stripped. A typical paste looks like:
//
//     Mario Nawfal
//     @MarioNawfal
//     ·
//     1m
//     <tweet content, possibly multiple lines / bullet points>
//
//     Source: CBS News
//
// → { author: '@MarioNawfal', text: '<tweet content>', age: '1m',
//     source: 'CBS News', parsed: true }
//
// The parser is intentionally forgiving: anything it can't confidently
// classify is kept as body text, and if it never finds a handle it returns
// `parsed: false` so the caller can fall back to manual entry.

export interface ParsedTweet {
  /** Handle including the leading "@", or '' if none was found. */
  author: string
  /** Tweet body with metadata, engagement, and source lines removed. */
  text: string
  /** Relative age token as shown by X ("1m", "2h", "3d"), or ''. */
  age: string
  /** Value after a trailing "Source: …" line, or ''. */
  source: string
  /** True when a handle was found and the paste looked like a tweet. */
  parsed: boolean
}

const HANDLE_RE = /^@(\w{1,15})\b/
// Relative age, optionally led by the "·" separator X renders ("· 2h", "20m").
const REL_TIME_RE = /^[·•\s]*(\d+)\s*(s|m|h|d|w|y)$/i
// A separator-only line: "·" / "•".
const DOT_ONLY_RE = /^[·•\s]+$/
// "Source: CBS News" / "Source - Reuters".
const SOURCE_RE = /^source\s*[:\-]\s*(.+)$/i
// Engagement / metrics rows: "1.2K Replies · 3.4K Reposts", "12 Views".
const ENGAGEMENT_RE = /\b(repl|repost|retweet|like|view|bookmark)/i
// A line that is only counts and separators: "2 · 4 · 9", "1.2K".
const COUNTS_ONLY_RE = /^[\d.,kmb·•\s]+$/i

const isMeta = (line: string): boolean =>
  HANDLE_RE.test(line) ||
  REL_TIME_RE.test(line) ||
  DOT_ONLY_RE.test(line) ||
  ENGAGEMENT_RE.test(line) ||
  COUNTS_ONLY_RE.test(line)

export function parseTweetPaste(raw: string): ParsedTweet {
  const lines = raw
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.length > 0)

  let author = ''
  let age = ''
  let source = ''
  let handleIdx = -1
  const body: string[] = []

  lines.forEach((line, i) => {
    if (handleIdx === -1) {
      const m = HANDLE_RE.exec(line)
      if (m) {
        author = `@${m[1]}`
        handleIdx = i
        return
      }
    }

    if (!age) {
      const t = REL_TIME_RE.exec(line)
      if (t) {
        age = `${t[1]}${t[2].toLowerCase()}`
        return
      }
    }

    if (DOT_ONLY_RE.test(line)) return

    const s = SOURCE_RE.exec(line)
    if (s) {
      source = s[1].trim()
      return
    }

    if (ENGAGEMENT_RE.test(line) || COUNTS_ONLY_RE.test(line)) return

    body.push(line)
  })

  // The line directly above the handle is the display name; drop it as it is
  // redundant with the handle we keep as author.
  if (handleIdx > 0) {
    const displayName = lines[handleIdx - 1]
    if (!isMeta(displayName) && body[0] === displayName) {
      body.shift()
    }
  }

  return {
    author,
    text: body.join('\n').trim(),
    age,
    source,
    parsed: handleIdx !== -1
  }
}
