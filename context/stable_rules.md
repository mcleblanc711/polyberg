# Stable Rules Reference

## Hormuz Portwatch 60% 7DMA Rule

Markets using `hormuz_portwatch_60_7dma` resolve from the specified official data oracle.
For analysis, treat the oracle calculation as controlling unless the market rule text says a
fallback source can override it.

Key interpretation notes:

- Use the named official source before media narratives.
- Distinguish transit normalization from partial reopening headlines.
- Record the exact resolution window and moving-average definition before making a trade call.

## Blockade Lifted Announcement Rule

Markets using `official_blockade_lifted_announcement` require an explicit qualifying statement
from the named official actor or institution. Resumed shipping, leaks, or anonymous reporting are
not equivalent unless the market rules define a media fallback.

## CL HIGH Oil Price Rule

Markets using `nymex_cl_high_print` should be evaluated against the exchange contract and exact
price print specified by the market. Headlines about Brent, spot oil, or intraday estimates are not
substitutes unless the rules permit them.
