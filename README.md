![coldcore](docs/img/logo.png)


**This is experimental software. Wait for a formal release before use with real
funds.**

A trust-minimized Bitcoin wallet interface that relies only on Bitcoin Core.

- Zero install process for most platforms
- Designed for simplicity and auditability
- No GUI, terminal only
- Works in terms of script descriptors and PSBTs
- Minimal dependencies: Bitcoin Core, Python 3 interpreter, nothing else
- Supports only airgapped, opensource hardware wallets
- Integrates with GPG and [`pass`](https://www.passwordstore.org/) for secure xpub storage

In short, this is the easiest way to do air-gapped wallet management with Bitcoin Core,
Coldcard, and not much else.

---

- [Design](#design)
- [Status](#status)
- [Security assumptions](#security-assumptions)
- [Configuration](#configuration)
- [FAQ](#faq)
  - [Why is there no GUI?](#why-is-there-no-gui)
  - [Why do you only support Coldcard? Will you add others?](#why-do-you-only-support-coldcard-will-you-add-others)
  - [Why did you use Python and not {Rust,Haskell,C++}?](#why-did-you-use-python-and-not-rusthaskellc)
  - [Why do you encrypt the config file by default with GPG?](#why-do-you-encrypt-the-config-file-by-default-with-gpg)
                 
---


## Requirements

- Linux or MacOS
  - This has only been nominally tested on macOS so expect bugs
  - Support for Windows is planned, but I'll need someone with a Windows computer to
    help
- Bitcoin Core 0.18+
- Python 3.7+ (your system probably already has this)
- Coldcard

![home](docs/img/splash.png)

## Install process

1. Buy a [Coldcard](https://coldcardwallet.com)
1. Download, install, and sync [Bitcoin Core](https://bitcoincore.org/en/download/)
1. Ensure Python 3.7+ is on your system: `$ python3 --version` and if not, install it.
    - macOS: install [homebrew](https://brew.sh/), run `brew install python3`
    - [Linux](https://realpython.com/installing-python)
1. Clone this repo: `git clone https://github.com/jamesob/coldcore`
1. Make coldcore executable and run it
    - `cd coldcore; chmod +x coldcore; ./coldcore --help`
1. Optionally, install coldcore to your path
    - `cp coldcore ~/.local/bin/coldcore  # or somewhere on your PATH`
1. Boot 'er up
    - `coldcore`

### Verifying the install (optional but recommended)

1. Receive my keys in GPG:
  - `gpg --keyserver keyserver.ubuntu.com --recv-keys 0x25F27A38A47AD566`
  - You can verify this fingerprint on my Twitter: https://twitter.com/jamesob
1. Get the sigs for the release:
  - Get the signature: `curl -O http://img.jameso.be/sigs/coldcore-$(./coldcore --version).asc`
  - Verify the signature: `gpg coldcore-[version].asc`
  - Ensure it matches: `sha256sum coldcore`

## Design 

### Zero install process

As long as you have Bitcoin Core and a Python 3.7+ installation, you're ready to go. No
dealing with package managers, no worrying about dependencies, no setting up an
indexing server. This is just stdlib Python that likely shipped with your OS. We let
Core and Coldcard do the heavy lifting.

### Auditability

This project is designed to be auditable. It is a single executable script ~2000 LOC
written in straightforward, stdlib Python 3. Most programmers should be able to read
through in an hour.

### Minimal dependencies

Other wallets require indexing services that can take hours to provision (*after*
Core's initial block download), consume gigabytes of space, and are confusing to
configure even for software engineers.

This is a single script that most people with basic programming knowledge can at least
skim.

Other wallets require graphical runtimes (GUI toolkits, browsers) that not only entail
much more code, but are more prone to [exploits](https://snyk.io/vuln/npm:electron).
Handling wallet operations through Chrome isn't appropriate beyond a certain
point; browser authors could conceivably collect or manipulate data, and browsers are
often loaded with third-party plugins. Who wants to audit Qt? Not me.

![dashboard](docs/img/dashboard.png)

This script uses only terminal interfaces, and one of the design goals is to make them
approachable for people who haven't previously interacted with the command line much.
So if you've been wanting to learn about the shell, this is a pretty good opportunity.


```
github.com/AlDanial/cloc v 1.86  T=0.04 s (27.3 files/s, 84781.1 lines/s)
-------------------------------------------------------------------------------
Language                     files          blank        comment           code
-------------------------------------------------------------------------------
Python                           1            673            313           2123
-------------------------------------------------------------------------------
```

### Air-gapped hardware wallet support

This library will only support air-gapped interaction with hardware wallets that are
opensource. Right now, that means that Coldcard is the only key storage mechanism
supported, but I'm happy to add others that fit the criteria of

- being opensource, and
- supporting air-gapped interaction.


## Status

While this script is relatively simple, and I'm *pretty* sure there aren't any ways to
lose funds using it (knock wood), it is young and therefore in alpha. Some bugs are
only shallow under time, so unless you're a highly technical user who can scrutinize
the code pretty closely, hold off on using this for a few months.

I am using this code to manage my mainnet coins, but I don't recommend you do the same
until a stable release.

## Comparison to other wallets

Coldcore is very minimal in its feature set - it's basically just meant for sending
and receiving to singlesig keys on airgapped hardware wallets. That said, there are
plans to add multisig support in time.

Other wallets do much more than coldcard, but they are orders of magnitude greater
in terms of source code and therefore much harder to audit.

## Security assumptions

- Your xpub data is stored in a watch-only wallet in Bitcoin Core.
- This script doesn't touch your private keys.
- This script doesn't do any cryptography aside from optionally generating and
  checking xpub fingerprints.
- The configuration file for this script holds your xpub data. Your xpub data allows
  its holder to see all of your addresses. You can optionally encrypt this config file
  with GPG or pass.


## Configuration

### Environment variables

- `COLDCORE_CONFIG`: a path to your configuration. If this is of the form
  `pass:Some/Path`, it will run `pass show Some/Path` to retrieve your config. If
  the path ends in `.gpg`, we will use GPG to decrypt the configuration.

- `COLDCORE_GPG_KEY`: if you want to use GPG to encrypt your config file (without
  using pass), set this environment variable to the key to use for encryption. We
  will also read `~/.gnupg/gpg.conf` for the `default-key` setting.

### Global flags

#### `coldcore --rpc <url>`

Specify the Bitcoin Core RPC server. Useful if you're running Bitcoin Core on a
separate host. 

Note that RPC settings will be saved per wallet when running `coldcore setup`.

#### `coldcore -w <wallet-name>`

Denote the particular wallet to load if multiple exist in the config.

#### `coldcore --debug`

This generates a granular logfile of everything that happens, including stacktraces and
RPC communication.  Useful if something goes wrong.

**Be sure to delete the logfile** after use of this flag, as it contains xpub data. The
tool will remind you to do so.

## FAQ

### Why is there no GUI?

The terminal is debatably the safest primitive presentation mechanism with the least
cumulative code underlying it. Browers and GUI libraries are very complex. 

For basic wallet operations, a terminal interface should be more than sufficient,
especially when including curses.

### Why do you only support Coldcard? Will you add others?

Coldcard is the only wallet supported at the moment because it is
- opensource, and
- supports air-gapped use via PSBT.

If there are other hardware wallets that meet these criteria, create an issue. Pull
requests are certainly accepted.

### Why did you use Python and not {Rust,Haskell,C++}?

Python simultaneously comes installed nearly universally and is a high-level,
expressive language. Many people know it. This means that there are more potential
auditors or contributors for this project.

The same code written in another language might be twice as long, and would require
end users installing specialized compilers or dependencies.

There are advantages to shipping binaries to end-users, but because the emphasis here
is on trust minimization, I have opted to deliver human readable code. You can bring
your own Python implementation in whatever manner you like.

### Why do you encrypt the config file by default with GPG?

[This may change; I will probably repurpose the Coldcard AES code to do config file
encryption natively.]

I didn't want to have any serious crypto code in this library, and so I delegate
encryption to GPG rather than requiring a Python dependency that the end user might
have to install.
