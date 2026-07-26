"""Transaction Poller component (TR-1).

Decomposition:
- ``scheduler``          — drives poll cycles on a fixed interval (DD-1).
- ``enable_banking.gateway`` — authenticated Enable Banking API calls + pagination.
- ``enable_banking.adapter`` — anti-corruption mapping to the internal Transaction (DD-2).
- ``poller``             — wires them together and applies the settled-debit filter.
"""
