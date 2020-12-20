#!/usr/bin/env python3
"""
TODO

- [ ] add wallet name
- [ ] add version birthday to new config
- [ ] allow manual coin selection when sending
- [ ] address labeling
- [ ] implement scrolling in the curses balance panel
- [ ] implement --json, --csv
- [ ] implement command-on-monitor
- [ ] multisig workflow

"""

import logging
import re
import typing as t
import sys
import base64
import datetime
import subprocess
import time
import socket
import textwrap
import json
import io
import os
from pathlib import Path
from typing import Optional as Op
from dataclasses import dataclass, field
from configparser import ConfigParser
from decimal import Decimal

# fmt: off
# We have to keep these imports to one line because of how ./bin/compile works.
from .thirdparty.clii import App
from .thirdparty.bitcoin_rpc import RawProxy, JSONRPCError
from .crypto import xpub_to_fp
from .ui import start_ui, yellow, bold, green, red, GoSetup, OutputFormatter, DecimalEncoder
# fmt: on

__VERSION__ = "0.1.0-alpha"

root_logger = logging.getLogger()
logger = logging.getLogger("main")

BitcoinRPC = RawProxy

MAINNET = "mainnet"
TESTNET = "testnet3"

F = OutputFormatter()

cli = App()
cli.add_arg("--verbose", "-v", action="store_true", default=False)
cli.add_arg(
    "--config",
    "-c",
    action="store",
    default=None,
    help=(
        "Path to config file. Can be a `pass:Path/To/Config` or "
        "a filename ending in .gpg."
    ),
)
cli.add_arg("--debug", "-d", action="store_true", default=False)
cli.add_arg(
    "--testnet",
    action="store_true",
    default=False,
    help="Try to connect on the testnet network initially instead of mainnet.",
)
cli.add_arg(
    "--version",
    action="version",
    version=f"coldcore {__VERSION__}",
)
cli.add_arg(
    "--wallet",
    "-w",
    action="store",
    default=None,
    help="The specific wallet to open.",
)
cli.add_arg(
    "--rpc",
    "-r",
    action="store",
    default=None,
    help="The Bitcoin Core RPC interface URL to use, e.g. 'http://user:pass@host:8332'",
)

PASS_PREFIX = "pass:"


def setup_logging() -> Op[Path]:
    """
    Configure logging; only log when --debug is enabled to prevent unintentional
    data leaks.

    Returns a path to the logfile if one is being used.
    """
    # TODO base this on config?
    log_path = "coldcore.log"
    formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s - %(message)s")
    log_filehandler = logging.FileHandler(log_path)
    log_filehandler.setLevel(logging.DEBUG)
    log_filehandler.setFormatter(formatter)

    if cli.args.debug:
        root_logger.setLevel(logging.DEBUG)
        root_logger.addHandler(log_filehandler)
        logger.setLevel(logging.DEBUG)
        return Path(log_path)

    return None


@dataclass
class Wallet:
    """
    In-memory representation of a single BIP32 HD wallet. Often but not necessarily
    backed by a hardware wallet.
    """

    fingerprint: str
    deriv_path: str
    xpub: str

    # The name of the watch-only wallet stored in Bitcoin Core.
    bitcoind_name: str

    # TODO at some point we'll support non-WPKH descriptors.
    descriptors: t.List["WpkhDescriptor"] = field(default_factory=list)

    earliest_block: Op[int] = None
    bitcoind_json_url: Op[str] = None

    # If given, this was loaded from an external storage mechanism (e.g. pass, gpg).
    # Respect this when translating back to INI.
    loaded_from: Op[str] = None

    @property
    def name(self):
        """
        The coldcore name of the wallet; not necessarily the name of what is
        stored in bitcoind.
        """
        raise NotImplementedError

    @property
    def descriptor_base(self):
        return f"wpkh([{self.fingerprint}{self.deriv_path}]{self.xpub})"

    @property
    def net_name(self):
        if self.xpub.startswith("tpub"):
            return TESTNET
        elif self.xpub.startswith("xpub"):
            return MAINNET
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
        if self.loaded_from:
            # TODO it's incumbent upon the user to maintain this themmselves?
            return {"load_from": self.loaded_from}

        checksums = {}
        for d in self.descriptors:
            checksums.update(d.change_to_checksum)

        return {
            "fingerprint": self.fingerprint,
            "deriv_path": self.deriv_path,
            "xpub": self.xpub,
            "bitcoind_name": self.bitcoind_name,
            "bitcoind_json_url": self.bitcoind_json_url or "",
            "earliest_block": str(self.earliest_block or ""),
            "checksum_map": json.dumps(checksums),
        }

    @property
    def loaded_xpub(self):
        if not hasattr(self, "__loaded_xpub"):
            self.__loaded_xpub = self.__loaded_xpub.strip()
        return self.__loaded_xpub

    @classmethod
    def from_ini(cls, name: str, rpc: BitcoinRPC, conf: ConfigParser) -> "Wallet":
        this_conf = conf[name]
        load_from = this_conf.get("load_from")

        if load_from:
            content: Op[str] = ""
            if _is_pass_path(load_from):
                passpath = load_from.split(PASS_PREFIX, 1)[-1]
                content = Pass().read(passpath, action=f"Requesting wallet {name})")
            elif load_from.endswith(".gpg"):
                content = GPG().read(load_from)  # type: ignore
            else:
                raise ValueError(f"from directive unrecognized: {load_from}")

            if not content:
                raise ValueError(f"failed to retrieve config from {load_from}")

            conf2 = ConfigParser()
            try:
                conf2.read_string(content)
            except Exception:
                msg = f"Failed to read config for wallet {name} ({load_from})"
                logger.exception(msg)
                F.warn(msg)
                sys.exit(1)

            this_conf = conf2[name]

        fp = this_conf["fingerprint"]
        deriv_path = this_conf["deriv_path"]
        bitcoind_name = this_conf["bitcoind_name"]
        xpub = this_conf["xpub"]
        checksum_map = json.loads(this_conf["checksum_map"])
        url = this_conf.get("bitcoind_json_url")
        earliest_block = (
            int(this_conf.get("earliest_block") or 0) or None
        )  # type: ignore

        if set(checksum_map.keys()) != {"1", "0"}:
            raise ValueError(f"unexpected checksum map contents: {checksum_map}")

        descs = [
            WpkhDescriptor.from_conf(
                fp,
                deriv_path,
                xpub,
                is_change=is_change,
                checksum=checksum_map["1" if is_change else "0"],
            )
            for is_change in [False, True]
        ]

        return cls(
            fp,
            deriv_path,
            xpub,
            bitcoind_name,
            descs,
            earliest_block,
            url,
            loaded_from=load_from,
        )


class CCWallet(Wallet):
    """
    A wallet whose private key lives on a Coldcard device.
    """

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

        def desc_to_checksum(desc: WpkhDescriptor) -> str:
            try:
                return rpc.getdescriptorinfo(desc.base)["checksum"]
            except JSONRPCError:
                # TODO handle
                raise

        descs = []
        for is_change in [False, True]:
            desc = WpkhDescriptor.from_conf(
                fp, deriv_path, xpub, is_change=is_change, checksum=""
            )
            desc.checksum = desc_to_checksum(desc)
            descs.append(desc)

        return cls(
            fp,
            deriv_path,
            xpub,
            f"coldcard-{fp.lower()}",
            descriptors=descs,
            earliest_block=earliest_block,
        )


@dataclass
class WpkhDescriptor:
    # The descriptor without the checksum.
    base: str
    checksum: str
    # Does this descriptor correspond to a change wallet?
    is_change: bool

    @property
    def with_checksum(self):
        return f"{self.base}#{self.checksum}"

    @property
    def change_to_checksum(self):
        key = "1" if self.is_change else "0"
        return {key: self.checksum}

    @classmethod
    def from_conf(
        cls,
        fingerprint: str,
        deriv_path: str,
        xpub: str,
        is_change: bool,
        checksum: str,
    ) -> "WpkhDescriptor":
        change = 1 if is_change else 0
        base = f"wpkh([{fingerprint.lower()}{deriv_path}]{xpub}/{change}/*)"
        return cls(base, checksum, is_change)


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
    """Used to proxy logic into the terminal UI."""

    def create_config(self, p: str, url: str) -> "GlobalConfig":
        return create_config(p, url)

    def parse_cc_public(self, contents: str, rpc: BitcoinRPC) -> CCWallet:
        return CCWallet.from_io(io.StringIO(contents), rpc)

    def rpc_wallet_create(self, *args, **kwargs):
        return rpc_wallet_create(*args, **kwargs)

    def discover_rpc(self, *args, **kwargs) -> Op[BitcoinRPC]:
        return discover_rpc(*args, **kwargs)

    def has_gpg(self) -> bool:
        return _get_gpg_command()

    def has_pass(self) -> bool:
        return _get_stdout("which pass")[0] == 0

    def suggested_config_path(self, use_gpg: bool = False) -> str:
        return get_path_for_new_config(use_gpg)

    def get_utxos(self, rpcw):
        return get_utxos(rpcw)

    def prepare_send(self, *args, **kwargs) -> str:
        return _prepare_send(*args, **kwargs)

    def psbt_to_tx_hex(self, *args, **kwargs) -> str:
        return _psbt_to_tx_hex(*args, **kwargs)

    def confirm_broadcast(self, *args, **kwargs) -> bool:
        return confirm_broadcast(*args, **kwargs)


def discover_rpc(
    config: Op["GlobalConfig"] = None, url: Op[str] = None
) -> Op[BitcoinRPC]:
    """Return an RPC connection to Bitcoin if possible."""
    service_url = None

    if cli.args.rpc:
        service_url = cli.args.rpc
    elif config:
        service_url = config.bitcoind_json_url
    elif url:
        service_url = url

    for i in (MAINNET, TESTNET):
        try:
            logger.info(f"trying RPC for {i} at {service_url}")
            rpc = get_rpc(service_url, net_name=i)
            rpc.help()
            logger.info(f"found RPC connection at {rpc.url}")
        except Exception:
            logger.debug("couldn't connect to Core RPC", exc_info=True)
        else:
            return rpc
    return None


def get_rpc(
    url: Op[str] = None,
    wallet: Op[Wallet] = None,
    quiet: bool = False,
    **kwargs,
) -> BitcoinRPC:
    """
    Get a connection to some Bitcoin JSON RPC server. Handles connection caching.

    If connecting to a wallet, ensure the wallet is loaded.
    """
    if not hasattr(get_rpc, "_rpc_cache"):
        setattr(get_rpc, "_rpc_cache", {})
    cache = get_rpc._rpc_cache  # type: ignore

    wallet_name = wallet.name if wallet else ""
    cache_key = (wallet_name, url)

    if cache_key in cache:
        return cache[cache_key]

    if not wallet:
        got = _get_rpc_inner(url, **kwargs)
        cache[cache_key] = got
    else:
        plain_rpc = _get_rpc_inner(url, net_name=wallet.net_name, **kwargs)
        try:
            # We have to ensure the wallet is loaded before accessing its
            # RPC.
            plain_rpc.loadwallet(wallet.name)
        except JSONRPCError as e:
            # Wallet already loaded.
            if e.error.get("code") != -4:  # type: ignore
                raise
        cache[cache_key] = _get_rpc_inner(
            url, net_name=wallet.net_name, wallet_name=wallet.name, **kwargs
        )

    return cache[cache_key]


def _get_rpc_inner(
    url: Op[str] = None, timeout: int = (60 * 5), **kwargs
) -> BitcoinRPC:
    return BitcoinRPC(
        url,
        timeout=timeout,
        debug_stream=(sys.stderr if cli.args.debug else None),
        **kwargs,
    )


@dataclass
class GlobalConfig:
    """Coldcore-specific configuration."""

    loaded_from: str
    raw_config: ConfigParser
    bitcoind_json_url: Op[str] = None
    default_wallet: Op[str] = None
    stdout: t.IO = sys.stdout
    stderr: t.IO = sys.stderr
    wizard_controller: WizardController = WizardController()

    disable_echo: bool = False

    # If true, skip anything that would block on user input.
    no_interaction: bool = False

    # Which GPG key should we encrypt with?
    # See: gnupg.org/documentation/manuals/gnupg/GPG-Configuration-Options.html
    gpg_default_key: Op[str] = os.environ.get("COLDCORE_GPG_KEY")

    def rpc(self, wallet: Op[Wallet] = None, **kwargs) -> BitcoinRPC:
        return get_rpc(cli.args.rpc or self.bitcoind_json_url, wallet, **kwargs)

    def exit(self, code):
        # To be overridden in unittests.
        sys.exit(code)

    @classmethod
    def from_ini(
        cls, loaded_from: str, conf: ConfigParser
    ) -> t.Tuple["GlobalConfig", t.List[Wallet]]:
        sect = conf["default"]
        c = cls(
            loaded_from,
            conf,
            sect.get("bitcoind_json_url"),
            sect.get("default_wallet"),
        )
        wallets = []

        for key in conf.sections():
            if key == "default":
                continue

            net_name = "mainnet"
            WalletClass = {"coldcard": CCWallet}.get(key.split("-")[0])

            if not WalletClass:
                raise ValueError(f"unrecognized wallet type for {key}")

            if conf[key].get("xpub", "").startswith("tpub"):
                net_name = TESTNET
            rpc = c.rpc(net_name=net_name)

            try:
                wallets.append(WalletClass.from_ini(key, rpc, conf))
            except Exception:
                msg = f"Unable to read config section '{key}'"
                logger.exception(msg)
                c.err(msg)

        return (c, wallets)

    @classmethod
    def write_blank(cls, outfile: t.IO, bitcoind_json_url: Op[str] = ""):
        """Write a blank configuration file."""
        outfile.write(_get_blank_conf(bitcoind_json_url))
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
        if _is_pass_path(self.loaded_from):
            to_path = self.loaded_from.split(PASS_PREFIX)[-1]
            passobj = Pass()
            content = io.StringIO()
            self.raw_config.write(content)
            content.seek(0)
            passobj.write(to_path, content.read())

        elif self.loaded_from.endswith(".gpg"):
            gpg = GPG()
            content = io.StringIO()
            self.raw_config.write(content)
            content.seek(0)
            gpg.write(self.loaded_from, content.read())

        else:
            with open(self.loaded_from, "w") as f:
                self.raw_config.write(f)

        logger.info(f"Wrote configuration to {self.loaded_from}")


def _get_blank_conf(bitcoind_json_url: Op[str] = "") -> str:
    return textwrap.dedent(
        f"""
        [default]

        # If blank, this will default to something like
        #   http://localhost:8332
        # You can specify non-localhosts like
        #   http://your_rpc_user:rpcpassword@some_host:8332/
        bitcoind_json_url = {bitcoind_json_url or ''}

        # This corresponds to one of the wallet sections listed below,
        # and will be used for commands where a single wallet is required
        # but unspecified.
        default_wallet =
        """
    )


def _get_stdout(*args, **kwargs) -> t.Tuple[int, bytes]:
    """Return (returncode, stdout as bytes)."""
    kwargs["shell"] = True
    kwargs["capture_output"] = True
    result = subprocess.run(*args, **kwargs)
    return (result.returncode, result.stdout)


def _sh(*args, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("shell", True)
    return subprocess.run(*args, **kwargs)


def rpc_wallet_create(rpc: BitcoinRPC, wall: Wallet):
    try:
        rpc.createwallet(wall.bitcoind_name, True)
    except JSONRPCError as e:
        if e.error.get("code") != -4:  # type: ignore
            # Wallet already exists; ok.
            raise


def get_utxos(rpcw: BitcoinRPC) -> t.Dict[str, "UTXO"]:
    return {
        u.address: u
        for u in UTXO.from_listunspent(rpcw.listunspent(0))  # includes unconfirmed
    }


def _prepare_send(
    config: GlobalConfig,
    rpcw: BitcoinRPC,
    to_address: str,
    amount: str,
    spend_from: Op[t.List[str]],
):
    vins = []

    if spend_from:
        utxos = UTXO.from_listunspent(rpcw.listunspent(0))
        addrs = {u.address for u in utxos}
        unknown_addrs = set(spend_from) - addrs

        for addr in unknown_addrs:
            # TODO should fail?
            F.warn(f"WARNING: address '{addr}' not in wallet")

        for u in utxos:
            if u.address in spend_from:
                vins.append({"txid": u.txid, "vout": u.vout})

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
            F.warn(f"Bad address specified: {e}")
            return False
        raise

    nowstr = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"unsigned-{nowstr}.psbt"
    Path(filename).write_bytes(base64.b64decode(result["psbt"]))
    info = rpcw.decodepsbt(result["psbt"])
    num_inputs = len(info["inputs"])
    num_outputs = len(info["outputs"])

    fee = result["fee"]
    perc = (fee / Decimal(amount)) * 100
    F.info(f"{num_inputs} inputs, {num_outputs} outputs")
    F.info(f"fee: {result['fee']} BTC ({perc:.2f}% of amount)")
    F.done(f"wrote PSBT to {filename} - sign with coldcard")

    return filename


def _psbt_to_tx_hex(rpcw: BitcoinRPC, psbt_path: Path) -> str:
    content: bytes = psbt_path.read_bytes().strip()

    # Handle signed TX as raw binary.
    if content[0:5] == b"psbt\xff":
        to_ascii = base64.b64encode(content).decode()
        # TODO handle errors
        return rpcw.finalizepsbt(to_ascii)["hex"]

    # Handle signed TX as base64.
    elif content[0:6] == b"cHNidP":
        # TODO handle errors
        return rpcw.finalizepsbt(content.decode())["hex"]

    # Handle signed TX as hex.
    elif _can_decode_transaction(rpcw, content.decode()):
        return content.decode()

    raise ValueError("unrecognized signed PSBT format")


def _can_decode_transaction(rpc: BitcoinRPC, tx_hex: str) -> bool:
    try:
        got = rpc.decoderawtransaction(tx_hex)
        assert got["txid"]
    except Exception:
        return False
    return True


def confirm_broadcast(rpcw: BitcoinRPC, hex_val: str, psbt_hex: str) -> bool:
    """Display information about the transaction to be performed and confirm."""
    info = rpcw.decoderawtransaction(hex_val)
    psbtinfo = rpcw.decodepsbt(psbt_hex)
    outs: t.List[t.Tuple[str, Decimal]] = []

    for out in info["vout"]:
        addrs = ",".join(out["scriptPubKey"]["addresses"])
        outs.append((addrs, out["value"]))

    F.alert("About to send a transaction:\n")

    for i in psbtinfo["inputs"]:
        # TODO does this mean we only support segwit transactions?
        wit = i["witness_utxo"]
        amt = wit["amount"]
        address = wit["scriptPubKey"]["address"]

        amt = bold(red(f"{amt} BTC"))
        F.blank(f" <- {address}  ({amt})")

    F.p()

    for o in outs:
        try:
            addr_info = rpcw.getaddressinfo(o[0])
        except Exception:
            # TODO handle this
            raise

        amt = bold(green(f"{o[1]} BTC"))
        yours = addr_info["ismine"] or addr_info["iswatchonly"]
        yours_str = "  (your address)" if yours else ""
        F.blank(f" -> {bold(o[0])}  ({amt}){yours_str}")

    print()

    inp = input(f" {yellow('?')}  look okay? [y/N]: ").strip().lower()

    if inp != "y":
        return False
    return True


def _wallet_from_input(inp: str, rpc: BitcoinRPC) -> Wallet:
    inppath = Path(inp)
    if inp == "-":
        content = io.StringIO(sys.stdin.read())
    elif inppath.exists():
        content = io.StringIO(Path(inp).read_text())
    else:
        raise ValueError(f"input path {inppath} can't be read")

    return CCWallet.from_io(content, rpc)


@cli.cmd
def decodepsbt(fname: str, format: str = "json"):
    """
    Args:
        format: either json or hex
    """
    (config, (wall, *_)) = _get_config_required()
    rpc = config.rpc()
    b = Path(fname).read_bytes()
    hexval = base64.b64encode(b).decode()
    if format == "hex":
        print(hexval)
    else:
        print(json.dumps(rpc.decodepsbt(hexval), cls=DecimalEncoder))


@cli.cmd
def setup():
    """
    Run initial setup for a wallet. This creates the local configuration file (if
    one doesn't already exist) and populates a watch-only wallet in Core.
    """
    config, walls = _get_config(require_wallets=False)
    if config:
        config.disable_echo = True
    start_ui(config, walls, WizardController(), GoSetup)


def _run_scantxoutset(rpcw: BitcoinRPC, args, result):
    try:
        result["result"] = rpcw.scantxoutset(*args)
    except socket.timeout:
        logger.exception("socket timed out during txoutsetscan (this is expected)")


def _run_rescan(rpcw: BitcoinRPC, begin_height: int):
    try:
        rpcw.rescanblockchain(begin_height)
    except socket.timeout:
        logger.exception("socket timed out during rescan (this is expected)")


@cli.cmd
def watch():
    """Watch activity related to your wallets."""
    (config, (wall, *_)) = _get_config_required()
    rpcw = config.rpc(wall)

    utxos = get_utxos(rpcw)
    F.task(f"Watching wallet {config.wallet_name}")

    while True:
        new_utxos = get_utxos(rpcw)

        spent_addrs = utxos.keys() - new_utxos.keys()
        new_addrs = new_utxos.keys() - utxos.keys()

        for addr in spent_addrs:
            u = utxos[addr]
            F.info(f"Saw spend: {u.address} ({u.amount})")

        for addr in new_addrs:
            u = new_utxos[addr]
            F.info(f"Got new UTXO: {u.address} ({u.amount})")

        was_zeroconf = [new_utxos[k] for k, v in utxos.items() if v.num_confs == 0]
        finally_confed = [utxo for utxo in was_zeroconf if utxo.num_confs > 0]

        for u in finally_confed:
            F.info(f"UTXO confirmed! {u.address} ({u.amount})")

        utxos = new_utxos
        time.sleep(0.1)


@cli.cmd
def balance(format: str = "plain"):
    """
    Check your wallet balances.

    Args:
        format: can be plain, json, csv, or raw (for listunspent output)
    """
    (config, (wall, *_)) = _get_config_required()
    rpcw = config.rpc(wall)
    result = rpcw.listunspent(0)

    if format == "raw":
        print(json.dumps(result, cls=DecimalEncoder, indent=2))
        return

    utxos = UTXO.from_listunspent(result)  # includes unconfirmed
    sorted_utxos = sorted(utxos, key=lambda u: -u.num_confs)

    if format == "json":
        print(
            json.dumps([u.__dict__ for u in sorted_utxos], cls=DecimalEncoder, indent=2)
        )
        return

    for utxo in sorted_utxos:
        if format == "plain":
            print(f"{utxo.address:<40} {utxo.num_confs:>10} {utxo.amount}")
        elif format == "csv":
            print(f"{utxo.address},{utxo.num_confs},{utxo.amount}")

    if format == "plain":
        amt = sum(u.amount for u in utxos)
        print(bold(f"total: {len(utxos)} ({amt} BTC)"))


@cli.cmd
def prepare_send(to_address: str, amount: str, spend_from: str = ""):
    """
    Prepare a sending PSBT.

    Args:
        to_address: which address to send to
        amount: amount to send in BTC
        spend_from: comma-separated addresses to pull unspents from as inputs
    """
    (config, (wall, *_)) = _get_config_required()
    rpcw = config.rpc(wall)
    spend_from_list = spend_from.split(",") if spend_from else None

    return _prepare_send(config, rpcw, to_address, amount, spend_from_list)


@cli.cmd
def broadcast(signed_psbt_path: Path):
    """Broadcast a signed PSBT."""
    (config, (wall, *_)) = _get_config_required()
    rpcw = config.rpc(wall)
    hex_val = _psbt_to_tx_hex(rpcw, signed_psbt_path)
    psbt_hex = base64.b64encode(Path(signed_psbt_path).read_bytes()).decode()

    assert hex_val

    if not confirm_broadcast(rpcw, hex_val, psbt_hex):
        F.warn("Aborting transaction! Doublespend the inputs!")
        return

    got_hex = rpcw.sendrawtransaction(hex_val)
    F.done(f"tx sent: {got_hex}")
    print(got_hex)


@cli.cmd
def newaddr(num: int = 1):
    (config, (wall, *_)) = _get_config_required()
    rpcw = config.rpc(wall)

    for _ in range(num):
        print(rpcw.getnewaddress())


@cli.main
@cli.cmd
def ui():
    # TODO filter menu items based on wallet availability (only setup allowed)
    config, walls = _get_config(require_wallets=False)
    if config:
        config.disable_echo = True
    start_ui(config, walls, WizardController())


@cli.main
def main():
    """
    A trust-minimized wallet script.

    You can think of this as a thin layer of glue that sits between your
    air-gapped hardware wallet and Bitcoin Core.
    """
    ui()


class Pass:
    """Access to pass, the password store."""

    @classmethod
    def write(cls, path: str, content: str) -> bool:
        """Return True if write successful."""
        # TODO maybe detect whether or not we're overwriting and warn
        F.alert(f"Requesting to write to pass: {path}")
        logger.info(f"Writing to pass: {path}")
        proc = subprocess.Popen(
            f"pass insert -m -f {path}",
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.communicate(content.encode())
        return proc.returncode == 0

    @classmethod
    def read(self, path: str, action: str = "Requesting to read") -> Op[str]:
        """Return None if path doesn't exist."""
        F.alert(f"{action} from pass: {path}")
        logger.info(f"Reading from pass: {path}")
        retcode, conf_str = _get_stdout(f"pass show {path}")
        if retcode != 0:
            return None
        return conf_str.decode().strip()


class GPG:
    """Access to GPG."""

    def __init__(self):
        self.gpg_path: Op[str] = _get_gpg_command()

    @property
    def system_has_gpg(self):
        return bool(self.gpg_path)

    @classmethod
    def write(self, path: str, content: str) -> bool:
        """Return True if write successful."""
        logger.info(f"Writing to GPG: {path}")
        gpg_key = find_gpg_default_key()
        gpg_mode = f"-e -r {gpg_key}"

        if not gpg_key:
            F.info(
                "No default-key present; encrypting to GPG using a passphrase",
            )
            F.info(
                "(to use a default key, set envvar COLDCORE_GPG_KEY "
                "or default-key in gpg.conf)"
            )
            gpg_mode = "-c"

        with open(path, "w") as f:
            proc = subprocess.Popen(
                f"gpg {gpg_mode}", shell=True, stdout=f, stdin=subprocess.PIPE
            )
            proc.communicate(content.encode())

        return proc.returncode == 0

    @classmethod
    def read(self, path: str) -> Op[str]:
        p = Path(path)
        if not p.exists():
            logger.warning(f"tried to read from GPG path {p} that doesn't exist")
            return None

        logger.info(f"Reading from GPG: {path}")
        (retcode, content) = _get_stdout(f"gpg -d {p}")

        if retcode == 0:
            return content.decode().strip()

        logger.warning(f"failed to read GPG path {p}, returncode: {retcode}")
        return None


def find_gpg_default_key() -> Op[str]:
    """Get the GPG default-key to encrypt with."""
    gpg_conf_path = Path.home() / ".gnupg" / "gpg.conf"
    gpg_conf_lines = []
    key = os.environ.get("COLDCORE_GPG_KEY")
    if key:
        return key

    try:
        gpg_conf_lines = gpg_conf_path.read_text().splitlines()
    except FileNotFoundError:
        pass

    default_key_line = None
    try:
        [default_key_line] = [
            line for line in gpg_conf_lines if line.startswith("default-key ")
        ]
    except ValueError:
        pass

    if not default_key_line:
        logger.info(
            f"Must set `default-key` in {gpg_conf_path} or "
            "use COLDCORE_GPG_KEY envvar, otherwise don't know "
            "what to encrypt with.",
        )
        return None

    return default_key_line.split("default-key ")[-1]


CONFIG_DIR = Path.home() / ".config" / "coldcore"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.ini"


# TODO move config backend to prefix system


def _get_gpg_command() -> Op[str]:
    """Find the version, if any, of GPG installed."""
    if _get_stdout("which gpg2")[0] == 0:
        return "gpg2"
    elif _get_stdout("which gpg")[0] == 0:
        return "gpg"
    return None


def get_path_for_new_config(use_gpg=False) -> str:
    # FIXME: prefix backends
    gpg = _get_gpg_command()
    if gpg and use_gpg:
        return str(CONFIG_DIR / "config.ini.gpg")
    return str(CONFIG_DIR / "config.ini")


def find_default_config() -> Op[str]:
    """
    Find an existing default configuration file. We do this
    (vs. get_path_for_new_config) because a user may have created a configuration file
    and then installed GPG.
    """
    # Prefer GPG configs
    for ext in (".gpg", ""):
        path = CONFIG_DIR / ("config.ini" + ext)
        if path.exists():
            return str(path)
    return None


def _is_pass_path(p: Op[str]) -> bool:
    return bool(p) and p.startswith(PASS_PREFIX)  # type: ignore


def create_config(conf_path, bitcoind_json_url: str) -> Op[GlobalConfig]:
    """
    Write a new global config file out using some storage backend.
    """
    if not CONFIG_DIR.exists():
        # FIXME macOS
        CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    confp = ConfigParser()

    def confirm_overwrite() -> bool:
        if Path(conf_path).exists():
            prompt = (
                f"Are you sure you want to overwrite "
                f"the existing file at {conf_path}? [y/N] "
            )
            return input(prompt).lower() == "y"
        return True

    # Optionally, read the configuration from `pass`.
    if _is_pass_path(conf_path):
        passobj = Pass()
        passpath = conf_path.split(PASS_PREFIX, 1)[-1]
        msg = f"Creating blank configuration at {yellow(conf_path)}"
        logger.info(msg)
        F.info(msg)
        contents = _get_blank_conf(bitcoind_json_url)
        # config doesn't exist, so insert it
        if not passobj.write(passpath, contents):
            print(f"Failed to write new configuration to {conf_path}")
            return None

        confp.read_string(contents)

    # Or read from GPG
    elif conf_path.endswith(".gpg"):
        gpg = GPG()
        if not confirm_overwrite():
            return None
        msg = f"Creating blank configuration at {conf_path}"
        logger.info(msg)
        F.info(msg)
        contents = _get_blank_conf(bitcoind_json_url)
        # config doesn't exist, so insert it
        if not gpg.write(conf_path, contents):
            print(f"Failed to write new configuration to {conf_path}")
            return None
        confp.read_string(contents)

    # Or just read it from some file path.
    else:
        logger.info(f"Creating blank configuration at {conf_path}")
        if not confirm_overwrite():
            return None

        F.warn("WARNING: creating an unencrypted configuration file.")
        F.warn("Please consider installing GPG and/or pass to support config file ")
        F.warn("encryption. If someone gains access to your xpubs, they can ")
        F.warn("see all of your addresses.")

        with open(conf_path, "w") as f:
            GlobalConfig.write_blank(f, bitcoind_json_url)

        confp.read(conf_path)

    return GlobalConfig.from_ini(conf_path, confp)[0]


def _get_config_required(*args, **kwargs) -> t.Tuple[GlobalConfig, t.List[Wallet]]:
    ret = _get_config(*args, **kwargs)
    if not ret[0]:
        F.warn("Please ensure this file is readable or run `coldcore` -> setup")
        sys.exit(1)

    return ret  # type: ignore


def _get_config(
    wallet_names: Op[t.List[str]] = None,
    bitcoind_json_url: str = "",
    require_wallets: bool = True,
) -> t.Tuple[Op[GlobalConfig], Op[t.List[Wallet]]]:
    """
    Load in coldcore config from some source.

    Return the config and a list of loaded wallets. The config's default_wallet will
    be the first item in the list.
    """
    confp = ConfigParser()
    conf_path = cli.args.config or os.environ.get(
        "COLDCORE_CONFIG", find_default_config()
    )
    none = (None, None)

    if not conf_path:
        return none

    def fail():
        F.warn(f"Failed to read config from {conf_path}")

    # Optionally, read the configuration from `pass`.
    if _is_pass_path(conf_path):
        passobj = Pass()
        passpath = conf_path.split(PASS_PREFIX, 1)[-1]
        contents = passobj.read(passpath, action="Requesting to load configuration INI")

        if not contents:
            fail()
            return none

        confp.read_string(contents)

    # Or read from GPG
    elif conf_path.endswith(".gpg"):
        gpg = GPG()
        F.alert(f"Reading configuration from {conf_path} with GPG")
        contents = gpg.read(conf_path)

        if not contents:
            fail()
            return none

        confp.read_string(contents)

    # Or just read it from some file path.
    else:
        if not Path(conf_path).exists():
            fail()
            return none
        confp.read(conf_path)

    (conf, wallet_confs) = GlobalConfig.from_ini(conf_path, confp)

    logger.debug("loaded with config: %s", conf)
    logger.debug("loaded with wallets: %s", wallet_confs)

    unrecog_wallets = set(wallet_names or []) - set(w.name for w in wallet_confs)
    if unrecog_wallets:
        conf.err("Unrecognized wallet names: {', '.join(unrecog_wallets)}")
        conf.exit(1)

    if wallet_names:
        wallet_confs = [w for w in wallet_confs if w.name in wallet_names]

    default_wallet = cli.args.wallet or conf.default_wallet

    # Return the default wallet first.
    wallet_confs = sorted(
        wallet_confs, key=lambda w: w.name == default_wallet, reverse=True
    )

    if require_wallets and not wallet_confs:
        conf.err("At least one wallet config is required but none were found.")
        conf.err("Try running `coldcore setup --help` to set up a wallet")
        sys.exit(1)

    return (conf, wallet_confs)


def main():
    cli.parse_for_run()
    log_path = setup_logging()
    cli.run()

    if log_path:
        F.warn(
            f"WARNING: remove logfiles at {log_path} to prevent leaking sensitive data",
        )


if __name__ == "__main__":
    main()
