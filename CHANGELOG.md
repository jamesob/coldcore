- Move from `black` to `yapf` for formatting

## 0.4.1

- Added Coldcard Q support
- Fixed descriptor wallet import (setting active=true)
- Added QR printing
- Added `consolidate` CLI command
- Added coin selection interface for `consolidate`
- Change address type specified as bech32 upon wallet creation

## 0.3.1

- Wayland clipboard support (via wl-copy)
- Allow specification of fee_rate in prepare-send
- RPC fix for scriptPubKey addresses

## 0.1.0-alpha

- It's here!
- Tread lightly, report bugs, be wary of using with real money.

## 0.1.1-alpha

- RPC detection fix
- Remove `curses.A_ITALIC` use (fails on macOS)
- Rescan only when there are UTXOs


## 0.1.2-beta

- Improve various failure modes
  - RPC failures
  - Window resizes
- Fix UTXO unique-on-address assumption
- Beginning of Windows support (@billygarrison)


## 0.1.3

- Allow user-specified wallet names
- Bugfix: decoderawtransaction address/addresses RPC 
