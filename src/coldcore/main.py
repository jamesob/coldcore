#!/usr/bin/env python3
"""
TODO

- [ ] implement config
- [ ] xpub storage
- [ ] wizard
- [ ] disable logging in ui command, log to file
- [ ] implement --json, --csv
- [ ] implement command-on-monitor

To document:

- [ ] config


Security assumptions:

- xpub is stored in Core unencrypted

"""

import logging
import re
import typing as t
import sys
import base64
import datetime
import subprocess
import time
import textwrap
import io
from pathlib import Path
from typing import Optional as Op
from dataclasses import dataclass, field
from configparser import ConfigParser
from decimal import Decimal

from .thirdparty.clii import App
from .thirdparty.bitcoin_rpc import RawProxy, JSONRPCError
from .crypto import xpub_to_fp
from .ui import start_ui


root_logger = logging.getLogger()
logger = logging.getLogger(__name__)
log_filehandler = logging.FileHandler("coldcore.log")
log_filehandler.setLevel(logging.DEBUG)
logger.addHandler(log_filehandler)
logger.setLevel(logging.DEBUG)

BitcoinRPC = RawProxy

cli = App()
cli.add_arg("--verbose", "-v", action="store_true", default=False)
cli.add_arg("--config", "-c", action="store", default=None)
cli.add_arg("--debug", "-d", action="store_true", default=False)


CONFIG_DIR = Path.home() / ".config" / "coldcore"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.ini"
PASS_PREFIX = "pass:"


def setup_logging():
    if cli.args.debug:
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(logging.StreamHandler())
        root_logger.addHandler(log_filehandler)


@dataclass
class WalletDescriptor:
    # Without checksum
    base: str
    checksum: str
    is_change: bool

    @property
    def with_checksum(self):
        return f"{self.base}#{self.checksum}"

    @classmethod
    def from_rpc(
        cls,
        fingerprint: str,
        deriv_path: str,
        xpub: str,
        is_change: bool,
        rpc: BitcoinRPC,
    ) -> "WalletDescriptor":
        base = mk_desc(fingerprint.lower(), deriv_path, xpub, 1 if is_change else 0)
        try:
            checksum = rpc.getdescriptorinfo(base)["checksum"]
        except JSONRPCError:
            # TODO handle
            raise
        return cls(base, checksum, is_change)


def mk_desc(fingerprint: str, deriv_path: str, xpub: str, change: int) -> str:
    """Return a script descriptor for some part of the wallet."""
    return f"wpkh([{fingerprint}{deriv_path}]{xpub}/{change}/*)"


@dataclass
class Wallet:
    fingerprint: str
    deriv_path: str
    xpub: str
    descriptors: t.List[WalletDescriptor] = field(default_factory=list)
    earliest_block: Op[int] = None
    bitcoind_json_url: Op[str] = None

    @property
    def name(self):
        raise NotImplementedError

    @property
    def descriptor_base(self):
        return f"wpkh([{self.fingerprint}{self.deriv_path}]{self.xpub})"

    @property
    def net_name(self):
        if self.xpub.startswith("tpub"):
            return "testnet3"
        elif self.xpub.startswith("xpub"):
            return "mainnet"
        else:
            raise ValueError("unhandled xpub prefix")

    def scantxoutset_args(self) -> t.Tuple[str, t.List[str]]:
        return ("start", [d.with_checksum for d in self.descriptors])

    def importmulti_args(self) -> t.Tuple:
        # TODO: use scantxoutset to take a guess at the earliest we need to do a
        # full rescan.
        args = [
            {
                "desc": d.with_checksum,
                "internal": d.is_change,
                # TODO be more decisive about this gap limit. Right now it's sort of
                # arbitrary.
                "range": [0, 3000],
                # TODO be smarter about this
                # TODO timestamp seems to be disregarded in core?
                "timestamp": "now",
                "keypool": True,
                "watchonly": True,
            }
            for d in self.descriptors
        ]

        return (args,)

    @property
    def as_ini_dict(self) -> t.Dict:
        return {
            "fingerprint": self.fingerprint,
            "deriv_path": self.deriv_path,
            "xpub": self.xpub,
            "bitcoind_json_url": self.bitcoind_json_url or "",
            "earliest_block": str(self.earliest_block or ""),
        }

    @property
    def loaded_xpub(self):
        if not hasattr(self, "__loaded_xpub"):
            if self.xpub_descriptor.startswith(PASS_PREFIX):
                passpath = self.xpub_descriptor.split(PASS_PREFIX, 1)[-1]
                self.global_config.err(
                    "Retrieving coldcard info from pass...", file=sys.stderr
                )
                self.__loaded_xpub = get_stdout(f"pass show {passpath}").decode()
            elif self.xpub_descriptor.endswith(".gpg"):
                self.__loaded_xpub = get_stdout(
                    f"gpg -d {self.xpub_descriptor}"
                ).decode()
            else:
                self.__loaded_xpub = self.xpub_descriptor

            self.__loaded_xpub = self.__loaded_xpub.strip()

        return self.__loaded_xpub

    @classmethod
    def from_ini(cls, name: str, rpc: BitcoinRPC, conf: ConfigParser) -> "Wallet":
        this = conf[name]
        fp = this["fingerprint"]
        deriv_path = this["deriv_path"]
        xpub = this["xpub"]
        url = this.get("bitcoind_json_url")
        earliest_block = int(this.get("earliest_block") or 0) or None  # type: ignore

        descs = [
            WalletDescriptor.from_rpc(
                fp, deriv_path, xpub, is_change=is_change, rpc=rpc
            )
            for is_change in [False, True]
        ]

        return cls(fp, deriv_path, xpub, descs, earliest_block, url)


class CCWallet(Wallet):
    @property
    def name(self):
        return f"coldcard-{self.fingerprint.lower()}"

    @classmethod
    def from_io(
        cls, inp: t.IO, rpc: BitcoinRPC, earliest_block: Op[int] = None
    ) -> "CCWallet":
        """
        Instantiate a CCWallet from the public output generated by the
        coldcard.
        """
        # TODO test the shit out of this

        content = inp.read()
        as_lines = content.splitlines()
        xpub_prefix = "xpub"

        if re.search(r" => tpub", content):
            xpub_prefix = "tpub"

        masterpubkey = ""
        for idx, line in enumerate(as_lines):
            if "'master' extended public key" in line:
                masterpubkey = as_lines[idx + 2].strip()
                if not masterpubkey.startswith(xpub_prefix):
                    raise ValueError("file format unexpected: master key")

        # We don't do anything with the masterpubkey other than compute a
        # fingerprint based on it.
        fp = xpub_to_fp(masterpubkey).lower()
        del masterpubkey

        m = re.search(r"master key fingerprint: (?P<fp>[a-zA-Z0-9]+)", content)

        # Optionally verify the master key fingerprint with a second source.
        if m:
            fp2 = m.groupdict()["fp"].lower()

            if fp2 != fp:
                raise ValueError(f"fingerprints don't match: {fp} vs. {fp2}")

        m2 = re.search(
            f"m/84'(?P<deriv_suffix>\\S+) => {xpub_prefix}(?P<xpub>[a-zA-Z0-9]+)",
            content,
        )

        if not m2:
            raise ValueError("couldn't find xpub path")

        deriv_path = "/84h"
        suffix = m2.groupdict()["deriv_suffix"]

        if not re.fullmatch(r"(/\d+'?)+", suffix):
            raise ValueError(f"derivation path not expected: {suffix}")

        deriv_path += suffix.replace("'", "h")

        if not re.search(deriv_path.replace("h", "'") + f" => {xpub_prefix}", content):
            raise ValueError(f"inferred derivation path appears invalid: {deriv_path}")

        xpub: str = xpub_prefix + m2.groupdict()["xpub"]

        descs = [
            WalletDescriptor.from_rpc(
                fp, deriv_path, xpub, is_change=is_change, rpc=rpc
            )
            for is_change in [False, True]
        ]

        return cls(
            fp,
            deriv_path,
            xpub,
            descriptors=descs,
            earliest_block=earliest_block,
        )


@dataclass
class UTXO:
    address: str
    amount: Decimal
    num_confs: int
    txid: str
    vout: int

    @classmethod
    def from_listunspent(cls, rpc_outs: t.List[t.Dict]) -> t.List["UTXO"]:
        return [
            cls(
                out["address"],
                out["amount"],
                out["confirmations"],
                out["txid"],
                out["vout"],
            )
            for out in rpc_outs
        ]


class WizardController:
    def create_config(self) -> "GlobalConfig":
        if not CONFIG_DIR.exists():
            # FIXME macOS
            CONFIG_DIR.mkdir(mode=0o700, parents=True)

        if not DEFAULT_CONFIG_PATH.exists():
            with open(DEFAULT_CONFIG_PATH, "w") as f:
                GlobalConfig.write_blank(f)

        cf = ConfigParser()
        cf.read(DEFAULT_CONFIG_PATH)
        return GlobalConfig.from_ini(str(DEFAULT_CONFIG_PATH), cf)[0]

    def parse_cc_public(self, contents: str, rpc: BitcoinRPC) -> CCWallet:
        return CCWallet.from_io(io.StringIO(contents), rpc)

    def rpc_wallet_create(self, *args, **kwargs):
        return rpc_wallet_create(*args, **kwargs)


@dataclass
class GlobalConfig:
    loaded_from: str
    raw_config: ConfigParser
    bitcoind_json_url: Op[str] = None
    default_wallet: Op[str] = None
    stdout: t.IO = sys.stdout
    stderr: t.IO = sys.stderr
    wizard_controller: WizardController = WizardController()

    def echo(self, *args, **kwargs):
        print(*args, file=self.stdout, **kwargs)

    def err(self, *args, **kwargs):
        print(*args, file=self.stderr, **kwargs)

    def exit(self, code):
        # To be overridden in unittests.
        sys.exit(code)

    def rpc(self, wallet: Op[Wallet] = None, **kwargs) -> BitcoinRPC:
        if wallet:
            plain_rpc = self._rpc(net_name=wallet.net_name, **kwargs)
            try:
                plain_rpc.loadwallet(wallet.name)
            except JSONRPCError as e:
                # Wallet already loaded.
                if e.error.get("code") != -4:  # type: ignore
                    raise
            return self._rpc(
                net_name=wallet.net_name, wallet_name=wallet.name, **kwargs
            )
        return self._rpc(**kwargs)

    def _rpc(
        self, url: Op[str] = None, timeout: int = (60 * 5), **kwargs
    ) -> BitcoinRPC:
        logger.info(url)
        return BitcoinRPC(
            url or self.bitcoind_json_url,
            timeout=timeout,
            debug_stream=(sys.stderr if cli.args.debug else None),
            **kwargs,
        )

    @classmethod
    def from_ini(
        cls, loaded_from: str, conf: ConfigParser
    ) -> t.Tuple["GlobalConfig", t.List["Wallet"]]:
        sect = conf["default"]
        c = cls(
            loaded_from,
            conf,
            sect.get("bitcoind_json_url", None),
            sect.get("default_wallet"),
        )
        wallets = []

        for key in conf.sections():
            if key != "default":
                net_name = "mainnet"

                WalletClass = {"coldcard": CCWallet}.get(key.split("-")[0])

                if not WalletClass:
                    raise ValueError(f"unrecognized wallet type for {key}")

                if conf[key].get("xpub", "").startswith("tpub"):
                    net_name = "testnet3"
                rpc = c.rpc(net_name=net_name)
                try:
                    wallets.append(WalletClass.from_ini(key, rpc, conf))
                except Exception:
                    msg = f"Unable to read config section '{key}'"
                    logger.exception(msg)
                    c.err(msg)

        return (c, wallets)

    @classmethod
    def write_blank(cls, outfile: t.IO):
        """Write a blank configuration file."""
        outfile.write(
            textwrap.dedent(
                """
            [default]

            # If blank, this will default to something like
            #   http://localhost:8332
            # You can specify non-localhosts like
            #   http://your_rpc_user:rpcpassword@some_host:8332/
            bitcoin_json_url =

            # This corresponds to one of the wallet sections listed below,
            # and will be used for commands where a single wallet is required
            # but unspecified.
            default_wallet =
            """
            )
        )

        p = Path(outfile.name)

        # Ensure that the created file is only readable by the owner.
        if p.exists():
            # FIXME make cross-platform
            _sh(f"chmod 600 {p}")

    def add_new_wallet(self, w: Wallet):
        logger.info("Adding new wallet to config: %s", w.as_ini_dict)
        self.raw_config[w.name] = w.as_ini_dict

    def write(self):
        """Save the contents of this config to an INI file on disk."""
        if self.loaded_from.startswith(PASS_PREFIX):
            raise ValueError("can't write config back to pass")

        with open(self.loaded_from, "w") as f:
            self.raw_config.write(f)


def get_stdout(*args, **kwargs) -> bytes:
    kwargs["shell"] = True
    kwargs["capture_output"] = True
    return subprocess.run(*args, **kwargs).stdout


def _sh(*args, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("shell", True)
    return subprocess.run(*args, **kwargs)


def rpc_wallet_create(rpc: BitcoinRPC, wall: Wallet):
    try:
        rpc.createwallet(wall.name, True)
    except JSONRPCError as e:
        if e.error.get("code") != -4:  # type: ignore
            # Wallet already exists; ok.
            raise


@cli.cmd
def setup():
    """Run initial setup for a wallet."""
    config, [wall] = get_config()
    rpc = config.rpc()
    rpcw = config.rpc(wall)

    rpc_wallet_create(rpc, wall)
    config.echo(rpcw.importmulti(*wall.importmulti_args()))
    config.echo(rpcw.rescanblockchain(610000))
    # TODO: above call will block. run in thread and poll with getwalletinfo.
    return True


@cli.cmd
def watch():
    """Watch activity related to your wallets."""
    config, [wall] = get_config()
    rpcw = config.rpc(wall)

    def get_utxos() -> t.Dict[str, "UTXO"]:
        return {
            u.address: u
            for u in UTXO.from_listunspent(rpcw.listunspent(0))  # includes unconfirmed
        }

    utxos = get_utxos()
    config.echo(f"Watching wallet {config.wallet_name}")

    while True:
        new_utxos = get_utxos()

        spent_addrs = utxos.keys() - new_utxos.keys()
        new_addrs = new_utxos.keys() - utxos.keys()

        for addr in spent_addrs:
            u = utxos[addr]
            config.echo(f"Saw spend: {u.address} ({u.amount})")

        for addr in new_addrs:
            u = new_utxos[addr]
            config.echo(f"Got new UTXO: {u.address} ({u.amount})")

        was_zeroconf = [new_utxos[k] for k, v in utxos.items() if v.num_confs == 0]
        finally_confed = [utxo for utxo in was_zeroconf if utxo.num_confs > 0]

        for u in finally_confed:
            config.echo(f"UTXO confirmed! {u.address} ({u.amount})")

        utxos = new_utxos
        time.sleep(0.1)


@cli.cmd
def balance():
    """Check your wallet balances."""
    config, [wall] = get_config()
    rpcw = config.rpc(wall)
    utxos = UTXO.from_listunspent(rpcw.listunspent(0))  # includes unconfirmed
    utxos = sorted(utxos, key=lambda u: -u.num_confs)

    for utxo in utxos:
        config.echo(f"{utxo.address:<40} {utxo.num_confs:>10} {utxo.amount}")

    amt = sum(u.amount for u in utxos)
    config.echo(f"total: {len(utxos)} ({amt})")
    return True


@cli.cmd
def prepare_send(to_address: str, amount: str, spend_from: str = ""):
    """
    Prepare a sending PSBT.

    Args:
        to_address: which address to send to
        amount: amount to send in BTC
        spend_from: comma-separated addresses to pull unspents from as inputs
    """
    config, [wall] = get_config()
    rpcw = config.rpc(wall)
    spend_from_ls = spend_from.split(",")
    vins = []

    if spend_from_ls:
        utxos = UTXO.from_listunspent(rpcw.listunspent(0))
        addrs = {u.address for u in utxos}
        unknown_addrs = set(spend_from_ls) - addrs

        for addr in unknown_addrs:
            # TODO should fail?
            config.echo(f"WARNING: address '{addr}' not in wallet")

        for u in utxos:
            if u.address in spend_from:
                vins.append({"txid": u.txid, "vout": u.vout})

    # Check to see if we own this address with getaddressinfo

    try:
        result = rpcw.walletcreatefundedpsbt(
            vins,  # inputs for txn (manual coin control)
            [{to_address: amount}],
            0,  # locktime
            {"includeWatching": True},  # options; 'feeRate'?
            True,  # bip32derivs - include BIP32 derivation paths for pubkeys if known
        )
    except Exception as e:
        # error code: -5 indicates bad address; handle that.
        if e.error.get("code") == -5:  # type: ignore
            config.echo(f"Bad address specified: {e}")
            return False
        raise

    nowstr = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"unsigned-{nowstr}.psbt"
    Path(filename).write_bytes(base64.b64decode(result["psbt"]))

    config.echo(result)
    config.echo(f"Wrote PSBT to {filename} - sign with coldcard")


@cli.cmd
def broadcast(signed_psbt_path: Path):
    """Broadcast a signed PSBT."""
    config, [wall] = get_config()
    rpcw = config.rpc(wall)
    content: bytes = signed_psbt_path.read_bytes().strip()
    hex_val: str = ""

    # Handle signed TX as raw binary.
    if content[0:5] == b"psbt\xff":
        to_ascii = base64.b64encode(content).decode()
        # TODO handle errors
        hex_val = rpcw.finalizepsbt(to_ascii)["hex"]

    # Handle signed TX as base64.
    elif content[0:6] == b"cHNidP":
        # TODO handle errors
        hex_val = rpcw.finalizepsbt(content.decode())["hex"]

    # Handle signed TX as hex.
    elif _can_decode_transaction(rpcw, content.decode()):
        hex_val = content.decode()

    else:
        raise ValueError("unrecognized signed PSBT format")

    assert hex_val
    if not _confirm_tx(config, rpcw, hex_val):
        return False
    config.echo(rpcw.sendrawtransaction(hex_val))
    return True


@cli.cmd
def newaddr():
    config, [wall] = get_config()
    rpcw = config.rpc(wall)
    config.echo(rpcw.getnewaddress())


@cli.cmd
def ui():
    """Start a curses UI."""
    config, walls = get_config()
    log_filehandler.setLevel(logging.DEBUG)
    root_logger.handlers = [log_filehandler]
    start_ui(config, walls)


def _can_decode_transaction(rpc: BitcoinRPC, tx_hex: str) -> bool:
    try:
        got = rpc.decoderawtransaction(tx_hex)
        assert got["txid"]
    except Exception:
        return False
    return True


def _confirm_tx(config: GlobalConfig, rpcw: BitcoinRPC, hex_val: str) -> bool:
    """Display information about the transaction to be performed and confirm."""
    info = rpcw.decoderawtransaction(hex_val)
    outs: t.List[t.Tuple[str, Decimal]] = []

    for out in info["vout"]:
        addrs = ",".join(out["scriptPubKey"]["addresses"])
        outs.append((addrs, out["value"]))

    config.echo("About to send a transaction:\n")
    for o in outs:
        try:
            addr_info = rpcw.getaddressinfo(o[0])
        except Exception:
            # TODO handle this
            raise

        yours = addr_info["ismine"] or addr_info["iswatchonly"]
        yours_str = "  (your address)" if yours else ""
        config.echo(f" -> {o[0]}  ({o[1]} BTC){yours_str}")

    config.echo("\n")

    inp = input("Look okay? [y/N]: ").strip().lower()

    if inp != "y":
        config.echo("Aborting transaction! Doublespend the inputs!")
        return False
    return True


def get_config(
    wallet_names: Op[t.List[str]] = None,
) -> t.Tuple[GlobalConfig, t.List[Wallet]]:
    confp = ConfigParser()
    conf_path = cli.args.config or DEFAULT_CONFIG_PATH

    # TODO this is okay for right now, but maybe think about making this less
    # automatic and more explicit.
    if conf_path == DEFAULT_CONFIG_PATH and not DEFAULT_CONFIG_PATH.exists():
        logger.info(f"Creating blank configuration at {DEFAULT_CONFIG_PATH}")
        with open(DEFAULT_CONFIG_PATH, "w") as f:
            GlobalConfig.write_blank(f)

    # Optionally, read the configuration from `pass`.
    if str(conf_path).startswith(PASS_PREFIX):
        passname = str(conf_path).split(PASS_PREFIX, 1)[-1]
        conf_str = get_stdout(f"pass show {passname}").decode()
        confp.read_string(conf_str)
    # Or just read it from some file path.
    else:
        confp.read(conf_path)
    (conf, wallet_confs) = GlobalConfig.from_ini(str(conf_path), confp)

    unrecog_wallets = set(wallet_names or []) - set(w.name for w in wallet_confs)
    if unrecog_wallets:
        conf.err("Unrecognized wallet names: {', '.join(unrecog_wallets)}")
        conf.exit(1)

    if wallet_names:
        wallet_confs = [w for w in wallet_confs if w.name in wallet_names]

    return (conf, wallet_confs)


if __name__ == "__main__":
    cli.parse_for_run()
    setup_logging()
    cli.run()
