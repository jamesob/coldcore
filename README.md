![coldcore](docs/img/logo.png)


**This is experimental software. Wait for a formal release before use with real
funds.**

A trust-minimized Bitcoin wallet interface

- Zero install process
- Never touches your key material
- Modern: works in terms of script descriptors and PSBTs
- Minimal dependencies: Bitcoin Core, Python 3 interpreter. No GUI, no indexing server,
  just Core RPC.
- Supports only airgapped, opensource hardware wallets
- Integrates with GPG and [`pass`](https://www.passwordstore.org/) for secure xpub storage


## Security assumptions

- Your xpub data is stored in a watch-only wallet in Bitcoin Core.

## Setup

- TODO minimum Bitcoin Core version?

## Configuration

### Environment variables

- `COLDCORE_CONFIG`: a path to your configuration. If this is of the form
  `pass:Some/Path`, it will run `pass show Some/Path` to retrieve your config. If
  the path ends in `.gpg`, we will use GPG to decrypt the configuration.

### Global flags

#### `coldcore --rpc <url>`

#### `coldcore --wallet <wallet-name>`

## FAQ

### Why did you use Python?

### Why do you encrypt the config file by default with GPG?
