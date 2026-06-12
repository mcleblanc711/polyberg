# Session Starter

Paste this at the top of a trading session. Fields marked (auto) are filled by
`polyberg fetch-books`, which writes the result to `live/session_starter.md`.
Fill the rest by hand before the session.

[1] Session started: {{generated_at}} (auto)

[2] Packet: attach the current research packet (`polyberg packet build`) and
    `polymarket_rules.md`.

[3] Markets with live books: {{live_book_markets}} (auto)

[4] Session intent: <what this session is for — e.g. reprice Hormuz ladders,
    review fills, new market intake>

## Session rules

- **No live book = no order.** Only price orders on market_ids listed in [3].
  Anything marked BOOK UNAVAILABLE in `live/order_books.md` gets no orders.
- Limit orders and sell ladders only — no market orders, no automation.
- Queue positions in the book report are APPROXIMATE: public books do not
  expose intra-level queue position.
