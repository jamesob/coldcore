<h1 align="center"><code>coldcore</code></h1>

<div align="center">Trust-minimized, airgapped Bitcoin management</div>

<br />
<div align="center">
  <a href="https://github.com/jamesob/coldcore/actions"><img src="https://github.com/jamesob/coldcore/workflows/build/badge.svg" alt="build"/></a>
</div>
<br />

**This is experimental software. Wait for a formal release before use with real
funds.**

A trust-minimized Bitcoin wallet interface that relies only on Bitcoin Core.

- Zero install process for most platforms
- Designed for simplicity and auditability
- No GUI, terminal only (curses and command-line)
- Works in terms of script descriptors and PSBTs
- Minimal dependencies: Bitcoin Core, Python 3 interpreter, nothing else
- Supports only airgapped, opensource hardware wallets
- Integrates with GPG and [`pass`](https://www.passwordstore.org/) for secure xpub storage

In short, this is the easiest way to do air-gapped wallet management with Bitcoin Core,
Coldcard, and not much else.

---

- [Design](#design)
- [Status](#status)
- [Usage](#Usage)
- [Security assumptions](#security-assumptions)
- [Configuration](#configuration)
- [FAQ](#faq)
  - [Why is there no GUI?](#why-is-there-no-gui)
  - [Why do you only support Coldcard? Will you add others?](#why-do-you-only-support-coldcard-will-you-add-others)
  - [Why did you use Python and not {Rust,Haskell,C++}?](#why-did-you-use-python-and-not-rusthaskellc)
  - [Why do you encrypt the config file by default with GPG?](#why-do-you-encrypt-the-config-file-by-default-with-gpg)
- [Donate](#donate)
- [TODO/Roadmap](#todo)

---


## Requirements

- Linux or MacOS
  - Support for Windows is planned, but I'll need someone with a Windows computer to
    help
- Bitcoin Core 0.19+
- Python 3.7+ (your system probably already has this)
- Coldcard

![home](docs/img/splash.png)

## macOS newbie-friendly install process

Not super familiar with the commandline? On macOS? Check out the [easy setup tutorial here.](docs/install-macos.md)

## Install process

1. Buy a [Coldcard](https://coldcardwallet.com)
1. Download, install, and sync [Bitcoin Core](https://bitcoincore.org/en/download/)
1. Ensure Python 3.7+ is on your system: `$ python3 --version` and if not, install it.
    - macOS: install [homebrew](https://brew.sh/), run `brew install python3`
    - [Linux](https://realpython.com/installing-python)
1. Clone this repo: `git clone https://github.com/jamesob/coldcore`
1. Optionally, install coldcore to your path
    - `cp coldcore ~/.local/bin/coldcore  # or somewhere on your PATH`
1. Boot 'er up
    - `coldcore`

### Verifying the install (optional but recommended)

1. Receive my keys in GPG:
    - `gpg --keyserver keyserver.ubuntu.com --recv-keys 0x25F27A38A47AD566`
    - You can verify this fingerprint on my Twitter: https://twitter.com/jamesob
1. Get the sigs for the release:
    - Get the signature
      - `curl -O http://img.jameso.be/sigs/coldcore-$(./coldcore --version | cut -d' ' -f2).asc`
    - Verify the signature
      - `gpg coldcore-[version].asc`
    - Ensure it matches
      - `sha256sum coldcore`

## Experimenting with testnet

If you're going to use this wallet, probably best to familiarize yourself with it
by doing a few test transactions in testnet.

1. Run Bitcoin Core locally with `-testnet`.
1. Set your Coldcard to work on testnet: `Settings > Blockchain > Testnet: BTC`
1. Run through the Coldcore setup flow: `coldcore setup`
    - Coldcore will autodetect your testnet RPC connection, however you can manually
      set `coldcard --rpc <url>` if desired.


### Development

Run tests and linting locally with `make test` and `make lint`. It's advisable to do
this before filing a PR, otherwise CI will likely fail due to [`black` formatting
requirements](https://github.com/psf/black).


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


### Air-gapped hardware wallet support

This library will only support air-gapped interaction with hardware wallets that are
opensource. Right now, that means that Coldcard is the only key storage mechanism
supported, but I'm happy to add others that fit the criteria of

- being opensource, and
- supporting air-gapped interaction.

### Auditing

All source is contained in `coldcore`.

## Status

While this script is relatively simple, and I'm fairly sure there aren't any
ways to lose funds using it (knock wood), it is young and in alpha. Some bugs
are only shallow under time, so unless you're a highly technical user who can
scrutinize the code pretty closely, hold off on using this for a few months.

I am using this code to manage my mainnet coins, but I don't recommend you do the same
until a stable release.

## Usage

### Receiving

You can use `newaddr` to generate addresses to receive to:

```sh
 % ./coldcore newaddr --help
usage: coldcore newaddr [-h] [--num NUM]

optional arguments:
  -h, --help  show this help message and exit
  --num NUM   default: 1
```

or just generate addresses and copy/paste from the dashboard view.

### Sending

To send, use a combination of `prepare-send` and `broadcast`:

```sh
% SEND_TO_ADDR=tb1qj2sjxuhxqyfgxkf6kqnthskqtum8hr2zr0l95j

% ./coldcore prepare-send $SEND_TO_ADDR 0.00001
 -- 1 inputs, 2 outputs
 -- fee: 0.00000141 BTC (14.10% of amount)
 ✔  wrote PSBT to unsigned-20201222-0920.psbt - sign with coldcard

% # I transfer the .psbt file to a microSD, sign with the coldcard, and plug
% # the microSD back in...

% ./coldcore broadcast /media/james/3264-6339/unsigned-20201222-0920-signed.psbt
 !  About to send a transaction:

     <- tb1qumfrma8gy08wcfq0ugwknh8cy0cdds5df8lfya  (0.00009859 BTC)

     -> tb1qj2sjxuhxqyfgxkf6kqnthskqtum8hr2zr0l95j  (0.00001000 BTC)  (your address)
     -> tb1qfs2yd54mmdzvrsnzdqk852crzclkn8cfx8cgzf  (0.00008718 BTC)  (your address)

 ?  look okay? [y/N]: y
 ✔  tx sent: d859cfe7a05e70e5d1e734244fb731c988bb29b236bd108529145cf987b8467f
d859cfe7a05e70e5d1e734244fb731c988bb29b236bd108529145cf987b8467f
```

## Comparison to other wallets

Coldcore is very minimal in its feature set - it's basically just meant for sending
and receiving to singlesig keys on airgapped hardware wallets. There are
plans to add multisig support.

Other wallets do much more than coldcore, but they are orders of magnitude greater
in terms of source code and therefore much harder to audit.

Coldcore weighs in at about 2100 lines of fairly readable code. And that's including
at least a few lines of stupid ASCII art and airy presentation logic.

```
github.com/AlDanial/cloc v 1.86  T=0.04 s (27.3 files/s, 84781.1 lines/s)
-------------------------------------------------------------------------------
Language                     files          blank        comment           code
-------------------------------------------------------------------------------
Python                           1            673            313           2123
-------------------------------------------------------------------------------
```

[Electrum](https://github.com/spesmilo/electrum/) is about 54,000 lines of Python,
and requires numerous dependencies and an indexing server.

```
% cloc electrum --exclude-dir=tests
     259 text files.
     258 unique files.
      27 files ignored.

github.com/AlDanial/cloc v 1.86  T=0.65 s (358.5 files/s, 124875.6 lines/s)
-------------------------------------------------------------------------------
Language                     files          blank        comment           code
-------------------------------------------------------------------------------
Python                         210           9305           8436          54293
JSON                             6              0              0           6178
SVG                             11              2              6           2730
Java                             1             14              2             73
Markdown                         2             21              0             49
Protocol Buffers                 1              2              8             37
F#                               2              2              0             12
-------------------------------------------------------------------------------
SUM:                           233           9346           8452          63372
-------------------------------------------------------------------------------
```

[Specter-desktop](https://github.com/cryptoadvance/specter-desktop) requires 5x
the Python this library does as well as a bunch of JavaScript.

```
% cloc src/cryptoadvance/specter
     192 text files.
     191 unique files.
      76 files ignored.

github.com/AlDanial/cloc v 1.86  T=0.23 s (525.5 files/s, 229720.5 lines/s)
-------------------------------------------------------------------------------
Language                     files          blank        comment           code
-------------------------------------------------------------------------------
JavaScript                      10           2296           5683          29037
Python                          53           1359           1236           9588
CSS                              2             24             33           1074
HTML                             7             42             28            878
SVG                             47              2             27            715
-------------------------------------------------------------------------------
SUM:                           119           3723           7007          41292
-------------------------------------------------------------------------------
```

These are both good products and I don't mean to disparage them, but personally I
think they are overkill for the kind of simple wallet operations I need to do.

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

The terminal is the simplest display layer with the least cumulative code underlying
it. Browsers and GUI libraries are very complex.

For basic wallet operations, a terminal interface should be more than sufficient,
especially when including curses.

### Why do you only support Coldcard? Will you add others?

Coldcard is the only wallet supported at the moment because it is
- opensource, and
- supports air-gapped use via PSBT.

If there are other hardware wallets that meet these criteria, create an issue. Pull
requests are certainly accepted.

### Why did you use Python and not {Rust,Haskell,C++}?

Python is already installed on most modern systems. It is a high-level,
expressive language which many people know. This means that there are more potential
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

## Donate

If you'd like to donate to this project, send Bitcoin to the address signed below
(`bc1qgyq7lxmk359c3vyxzz674pr8a9gnguxkgdw55p`), or
[sponsor me on Github](https://github.com/sponsors/jamesob).

```
-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

bc1qgyq7lxmk359c3vyxzz674pr8a9gnguxkgdw55p
-----BEGIN PGP SIGNATURE-----

iQIzBAEBCgAdFiEEGNRVI1NPYuZCSIrGepNdrbLETwUFAl/gLmsACgkQepNdrbLE
TwX8vg/+OZkL1+RbBjV8KNkqp7rQY/O1XXEOYX8JSYM+GEwmeACSGSbV6d7OqmTx
oofjmu5CJ93a2QpE8qPMIr2knRbUrfouAVzPqiF3RNp+UdEqdoLJkAox9MhXm9aG
d/PGYYx3Vf0Lq0bo6eUc19XU0bc38RRV0cjAwpKvfyc0u6SW/t6K6zjrXhZhcuga
LT6DqUxDXD5xDLpjeICDQgazraOr7QG8r39Yw5WSC95ewysiFOp/JQ5Zik6ut9LS
rXEX6+SqwQZOm0xcynqrYjFuiCdHGU39Eiy0DBXOTjeWQyBAq9pTRMXLId2dqyy1
iAbot2YmtNHuRH519YAakh4C0r2oFN7B2qQ2twIvt/rWtkmv3FWvcdKw6H0Q+4oc
VaD9S8cMVoR+bJEtY3EjLkUyd0zmxLuIgKSpdzchru07O/DhvvLvsNwgmzJMoD9f
iH3RfqMEJY+iAQFfoCA/sPwz56xWMW33Ta57+xfNSCTOtOLIJ5c0eqoCHoQ0PlAb
kJIEZ/S7qbbF1DGSlMG/Zbw8OHP0dBuKYjIev0CpFplQAV4SIzzOpxmVMQpahZjH
1RdH9J75+N2l4QgAWR0cJSxW0E56r3J94lM6fgieWySDsxteoAMXqWgLMEpMXNfA
Ze9i1ZlGxIIes25pRiyXXmwys3u1u8VOMmfiLe9VzStIJOMerIo=
=Q7Sw
-----END PGP SIGNATURE-----
```

## TODO

In rough order of priority:

- [ ] guide for CLI newbies
- [ ] allow manual coin selection when sending
- [ ] address labeling
- [ ] multisig workflow
- [ ] timelock scripts
- [ ] add wallet name to config
- [ ] add version birthday to new config
- [ ] implement scrolling in the curses balance panel

## Code from other projects

- [python-bitcoinlib](https://github.com/petertodd/python-bitcoinlib)
- [buidl-python](https://github.com/buidl-bitcoin/buidl-python)
