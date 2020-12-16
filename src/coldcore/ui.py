import curses
import contextlib
import typing as t
import logging
import time
import subprocess
from decimal import Decimal
from pathlib import Path
from collections import namedtuple
from typing import Optional as Op


logger = logging.getLogger("ui")

colr = curses.color_pair
bold = curses.A_BOLD


class Action:
    pass


class Scene:
    def set_configs(self, scr, conf, wconfs):
        self.scr = scr
        self.config = conf
        self.wallet_configs = wconfs
        self.controller = self.config.wizard_controller

    def draw(self, k: int) -> t.Tuple[int, Action]:
        pass


class MenuItem(namedtuple("MenuItem", "idx,title,action")):
    def args(self, mchoice):
        return (self.idx, self.title, mchoice == self)


class HomeScene(Scene):
    def __init__(self):
        super().__init__()

        self.setup_item = MenuItem(0, "start setup", GoSetup)
        self.monitor_item = MenuItem(1, "monitor wallet", GoHome)
        self.send_item = MenuItem(2, "send", GoHome)
        self.recieve_item = MenuItem(3, "receive", GoHome)

        self.mitems = [
            self.setup_item,
            self.monitor_item,
            self.send_item,
            self.recieve_item,
        ]

        self.midx = 0
        self.mchoice = self.setup_item

    def draw(self, k: int) -> t.Tuple[int, Action]:
        scr = self.scr
        curses.noecho()
        height, width = scr.getmaxyx()
        wconfigs = self.wallet_configs

        if k in [ord("q")]:
            return (-1, Quit)
        elif k in [curses.KEY_ENTER, 10, 13]:
            return (-1, self.mchoice.action)

        if k in [curses.KEY_DOWN, ord("j")] and self.midx < (len(self.mitems) - 1):
            self.midx += 1
        elif k in [curses.KEY_UP, ord("k")] and self.midx > 0:
            self.midx -= 1

        self.mchoice = self.mitems[self.midx]

        # Declaration of strings

        title: str = """
░█████╗░░█████╗░██╗░░░░░██████╗░░█████╗░░█████╗░██████╗░███████╗
██╔══██╗██╔══██╗██║░░░░░██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔════╝
██║░░╚═╝██║░░██║██║░░░░░██║░░██║██║░░╚═╝██║░░██║██████╔╝█████╗░░
██║░░██╗██║░░██║██║░░░░░██║░░██║██║░░██╗██║░░██║██╔══██╗██╔══╝░░
╚█████╔╝╚█████╔╝███████╗██████╔╝╚█████╔╝╚█████╔╝██║░░██║███████╗
░╚════╝░░╚════╝░╚══════╝╚═════╝░░╚════╝░░╚════╝░╚═╝░░╚═╝╚══════╝
    """

        title_len = len(title.splitlines()[2])
        subtitle = "your monetary glue"

        keystr = f"Wallets: {', '.join([w.name for w in wconfigs])}".format(k)[
            : width - 1
        ]

        # Centering calculations
        start_x_title = int((width // 2) - (title_len // 2) - title_len % 2)
        title_height = len(title.splitlines()) + 1

        start_y = height // 4
        title = "\n".join(
            ((" " * start_x_title) + line)[: width - start_y]
            for line in title.splitlines()
        )
        start_x_subtitle = int((width // 2) - (len(subtitle) // 2) - len(subtitle) % 2)
        start_x_keystr = int((width // 2) - (len(keystr) // 2) - len(keystr) % 2)

        with attrs(scr, colr(2), bold):
            scr.addstr(start_y, width // 2, title)

        scr.addstr(start_y + title_height, start_x_subtitle, subtitle[:width])
        scr.addstr(
            start_y + title_height + 2, start_x_title, ("/ " * (title_len // 2))[:width]
        )

        if wconfigs:
            scr.addstr(start_y + title_height + 4, start_x_keystr, keystr[:width])

        def menu_option(idx: int, text: str, selected=False):
            half = width // 2

            start_str = f'{"":<6}{text:>20}{"":<6}'
            if selected:
                start_str = " -> " + start_str[4:]
            scr.addstr(start_y + title_height + 8 + idx, half, start_str[:width])

        menu_option(*self.setup_item.args(self.mchoice))
        menu_option(*self.monitor_item.args(self.mchoice))
        menu_option(*self.send_item.args(self.mchoice))
        menu_option(*self.recieve_item.args(self.mchoice))

        scr.move(0, 0)

        # Refresh the screen
        scr.refresh()

        k = scr.getch()
        # Wait for next input
        return (k, GoHome)


class SetupScene(Scene):
    def __init__(self):
        self.bitcoin_rpc = None
        self.has_setup_coldcard = False
        self.cc_wallet: Op[t.Any] = None
        self.public_init_existed: Op[bool] = None
        self.public_contents: Op[str] = None
        self.opened_finder: Op[subprocess.Popen] = False
        self.wrote_config = False
        self.core_wallet_create = False
        self.core_imported = False
        self.core_scantxoutset = False
        self.scan_from_height = None
        self.have_rescanned = False
        self.chain_synced_info = None
        self.testaddress1 = None
        self.receive_utxo1 = None
        self.prepared_tx = None
        self.test_tx_hex = None
        self.test_tx_info = None
        self.confirm_send = False
        self.receive_utxo2 = None

        self.steps_xpos = 0
        self.steps_ypos = 0
        self.i = 0
        self.height = self.width = 0

    def new_step_line(self, msg, *attrs_, ypos: Op[int] = None) -> t.Tuple[int, int]:
        """Returns (y, x) of final cursor spot."""
        curr_ypos = ypos or self.steps_ypos
        with attrs(self.scr, *attrs_):
            self.scr.addstr(curr_ypos, self.steps_xpos, msg[: self.width])

        if ypos is None:
            self.steps_ypos += 1

        if self.steps_ypos >= (self.height - 2):
            # Scroll to make room
            self.scr.scrollok(True)
            self.scr.scroll((self.steps_ypos - self.height) + 2)

        return (curr_ypos, len(msg) + self.steps_xpos)

    def new_sec(self):
        self.steps_ypos += 1

    def draw(self, k: int) -> t.Tuple[int, Action]:
        scr = self.scr
        self.height, self.width = scr.getmaxyx()
        self.steps_ypos = 7

        self.i += 1
        if self.i % 1000 == 0:
            self.i = 0

        scr.timeout(400)

        title = f"""
              __
.-----.-----.|  |_.--.--.-----.
|__ --|  -__||   _|  |  |  _  |
|_____|_____||____|_____|   __| {'=' * (self.width - 39)}
                        |__|
"""
        y_start = 0
        x_start = 4
        self.steps_xpos = x_start + 4
        check_xpos = self.steps_xpos - 3

        title = "\n".join(
            ((" " * x_start) + line)[: (self.width - y_start)]
            for line in title.splitlines()
        )

        with attrs(scr, colr(2), bold):
            scr.addstr(y_start, x_start, title)

        def wait():
            """Return this when we're waiting on a step."""
            scr.refresh()
            return (scr.getch(), GoSetup)

        def delay_for_effect():
            scr.refresh()
            time.sleep(0.6)

        (core_ypos, _) = self.new_step_line("Searching for Bitcoin Core... ")
        box(scr, core_ypos, check_xpos)

        if not self.bitcoin_rpc:
            rpc = None
            try:
                self.bitcoin_rpc = self.controller.discover_rpc(self.config)

                if not self.bitcoin_rpc:
                    raise ValueError("no rpc found")

                delay_for_effect()
            except Exception:
                logger.exception("RPC failed")
                url = getattr(rpc, "url", "???")
                self.new_step_line(
                    f"Can't connect to Bitcoin Core (trying {url})", colr(2)
                )
                self.new_step_line(
                    "Try starting Bitcoin Core or editing your config at "
                    f"{self.config.loaded_from}",
                    colr(6),
                )
                return wait()

        testnet_str = " [testnet]" if self.bitcoin_rpc.net_name == "testnet" else ""
        self.new_step_line(
            f"Found it! ({self.bitcoin_rpc.public_url}){testnet_str}", colr(6)
        )
        green_check(scr, core_ypos, check_xpos)

        self.new_sec()
        (cc_ypos, cc_xpos) = self.new_step_line("Have you set up your coldcard? [Y/n] ")
        box(scr, cc_ypos, check_xpos)

        self.new_step_line("See: https://coldcardwallet.com/docs/quick", colr(4))

        if not self.has_setup_coldcard:
            if key_y(k):
                self.has_setup_coldcard = True
            else:
                scr.move(cc_ypos, cc_xpos)
                return wait()

        green_check(scr, cc_ypos, check_xpos)

        self.new_sec()
        (chain_ypos, chain_xpos) = self.new_step_line("Waiting for chain to sync...")
        box(scr, chain_ypos, check_xpos)

        if not self.chain_synced_info:
            # Really just for effect.
            delay_for_effect()

            chaininfo = self.bitcoin_rpc.getblockchaininfo()
            progress = chaininfo["verificationprogress"]

            if progress < 0.999:
                (chain_ypos, chain_xpos) = self.new_step_line(
                    f"Initial block download progress: {progress * 100:.2f}%"
                )
                scr.timeout(4000)
                return wait()
            else:
                self.chain_synced_info = chaininfo

        scr.timeout(400)
        self.new_step_line(
            f"Chain synced to height {self.chain_synced_info['blocks']}", colr(6)
        )
        green_check(scr, chain_ypos, check_xpos)

        self.new_sec()
        (pub_y, _) = self.new_step_line(
            "Export your Coldcard's public.txt and put it in this directory"
        )
        # TODO add spinner
        box(scr, pub_y, check_xpos)

        self.new_step_line(
            "See: https://coldcardwallet.com/docs/microsd#dump-summary-file",
            colr(4),
        )

        public = Path("./public.txt")
        if self.public_init_existed is None:
            self.public_init_existed = public.exists()

        if self.public_contents is None:
            delay_for_effect()
            if not self.public_init_existed:
                self.new_step_line(
                    "Here, I'll open a file explorer for you. Drop it in there.",
                    colr(4),
                )

                if not self.opened_finder:
                    self.opened_finder = subprocess.Popen(
                        "sleep 2; xdg-open .", shell=True
                    )

            if public.exists() and self.cc_wallet is None:
                self.public_contents = public.read_text()
                try:
                    self.cc_wallet = self.controller.parse_cc_public(
                        self.public_contents,
                        self.bitcoin_rpc,
                    )
                except Exception:
                    logger.exception("Failed to parse public.txt contents")
                    self.cc_wallet = ""
                    return wait()
            else:
                return wait()
        elif not self.cc_wallet:
            self.new_step_line(
                "Failed to extract wallet info from your public.txt!",
                colr(2),
            )
            self.new_step_line(
                "Check coldcore.log.",
                colr(2),
            )
            return wait()

        self.cc_wallet.bitcoind_json_url = self.bitcoin_rpc.url

        self.new_step_line("Parsed xpub as", colr(6))
        self.new_step_line(f"  {self.cc_wallet.descriptor_base}", colr(6))

        if not self.wrote_config:
            self.config.add_new_wallet(self.cc_wallet)
            self.config.write()
            self.wrote_config = True

        self.new_step_line(f"Wrote config to {self.config.loaded_from}")
        green_check(scr, pub_y, check_xpos)

        scr.refresh()

        self.new_sec()
        (core_y, _) = self.new_step_line("Setting up wallet in core")
        box(scr, core_y, check_xpos)

        rpc = self.bitcoin_rpc

        if not self.core_wallet_create:
            self.controller.rpc_wallet_create(rpc, self.cc_wallet)
            self.core_wallet_create = True

        # Long timeout for scanning.

        self.new_step_line(
            f"Created wallet {self.cc_wallet.name} in Core as watch-only", colr(6)
        )

        scr.refresh()

        if not self.core_imported:
            rpcw = self.config.rpc(self.cc_wallet, timeout=6000)
            rpcw.importmulti(*self.cc_wallet.importmulti_args())
            self.core_imported = True

        self.new_step_line("Imported descriptors 0/* and 1/* (change)", colr(6))
        (scan_y, scan_x) = self.new_step_line(
            "Scanning the UTXO set... (may take a few minutes)", colr(0)
        )

        scr.refresh()

        if not self.core_scantxoutset:
            rpcw = self.config.rpc(self.cc_wallet, timeout=6000)
            self.core_scantxoutset = rpcw.scantxoutset(
                *self.cc_wallet.scantxoutset_args()
            )

        unspents = self.core_scantxoutset["unspents"]
        if self.core_scantxoutset["unspents"]:
            bal = sum([i["amount"] for i in unspents])
            self.scan_from_height = min([i["height"] for i in unspents])
            self.new_step_line(
                f"Found a balance of {bal} BTC, earliest height: "
                f"{self.scan_from_height}",
                colr(5),
                bold,
                ypos=scan_y,
            )
        else:
            self.new_step_line(
                "Couldn't find a balance - new wallet eh?",
                colr(1),
                ypos=scan_y,
            )
        green_check(scr, core_y, check_xpos)

        scr.refresh()

        if self.scan_from_height:
            self.new_sec()
            (scanbc_y, _) = self.new_step_line(
                f"Scanning the chain history since block {self.scan_from_height}. "
                "I'd get a coffee tbh.",
                colr(0),
            )
            self.new_step_line(
                "This helps us index transactions associated with your coins.",
                colr(4),
            )

            scr.refresh()

            if not self.have_rescanned:
                rpcw = self.config.rpc(self.cc_wallet, timeout=0)
                box(scr, scanbc_y, check_xpos)
                scr.refresh()
                rpcw.rescanblockchain(self.scan_from_height)
                self.have_rescanned = True

            self.new_step_line("Scan complete", colr(6))
            green_check(scr, scanbc_y, check_xpos)

        self.new_sec()
        (testy, _) = self.new_step_line(
            "OK, now let's test your wallet by receiving a test transaction."
        )
        box(scr, testy, check_xpos)

        if not self.testaddress1:
            rpcw = self.config.rpc(self.cc_wallet)
            self.testaddress1 = rpcw.getnewaddress()

        self.new_step_line("Send a tiny test amount to")
        self.new_step_line("")
        self.new_step_line(f"    {self.testaddress1}", colr(2), bold)
        self.new_step_line("")
        (waity, waitx) = self.new_step_line("Waiting for transaction", colr(4), bold)

        if not self.receive_utxo1:
            scr.addstr(waity, waitx + 1, self._get_scroller())

            scr.timeout(2000)
            rpcw = self.config.rpc(self.cc_wallet)
            utxos = self.controller.get_utxos(rpcw)
            self.receive_utxo1 = utxos.get(self.testaddress1)

            if not self.receive_utxo1:
                return wait()

        self.new_step_line(
            f"Received amount of {self.receive_utxo1.amount} "
            f"({self.receive_utxo1.txid[:8]})",
            colr(5),
            bold,
            ypos=waity,
        )
        green_check(scr, testy, check_xpos)

        self.new_sec()
        (testy, _) = self.new_step_line("Now let's test your sending capabilities.")

        if not self.prepared_tx:
            rpcw = self.config.rpc(self.cc_wallet)
            self.toaddress1 = rpcw.getnewaddress()

            # Send 90% of the value over.
            # TODO this is only for testing and is potentially dangerous
            send_amt = str((self.receive_utxo1.amount * 9) / 10)
            self.prepared_tx = self.controller.prepare_send(
                self.config,
                rpcw,
                self.toaddress1,
                send_amt,
                [self.receive_utxo1.address],
            )

        self.new_step_line(
            f"You're going to send to another address you own, {self.toaddress1}."
        )
        self.new_step_line(f"I've prepared a transaction called '{self.prepared_tx}'")
        box(scr, testy, check_xpos)

        self.new_step_line(
            "Here, I'll open a file explorer for you.",
            colr(4),
        )

        self.new_step_line(
            "Transfer it to your coldcard via microSD from there.",
            colr(4),
        )

        if not self.opened_finder:
            self.opened_finder = subprocess.Popen("sleep 2; xdg-open .", shell=True)

        # TODO: coldcard specific?
        signed_filename = self.prepared_tx.replace(".psbt", "-signed.psbt")

        (wait2y, wait2x) = self.new_step_line(
            f"Waiting for the signed file ({signed_filename})", colr(4), bold
        )

        filepath = Path(signed_filename)
        if not filepath.exists():
            scr.addstr(wait2y, wait2x + 1, self._get_scroller())
            return wait()
        else:
            rpcw = self.config.rpc(self.cc_wallet)
            self.test_tx_hex = self.controller.psbt_to_tx_hex(rpcw, filepath)

        self.new_step_line("Cool, got the signed PSBT!", colr(6), bold)

        if not self.test_tx_info:
            rpcw = self.config.rpc(self.cc_wallet)
            self.test_tx_info = _get_tx_info(rpcw, self.test_tx_hex)

        assert len(self.test_tx_info) == 2
        self.new_step_line(f"  {self.test_tx_info[0]}", colr(0), bold)
        self.new_step_line("Confirm send? [y/n]", colr(2), bold)

        if not self.confirm_send:
            if key_y(k):
                self.confirm_send = True
                rpcw.sendrawtransaction(self.test_tx_hex)
            else:
                return wait()

        self.new_step_line("Transaction broadcast!", colr(2), bold)
        (waity2, waitx2) = self.new_step_line("Waiting for transaction", colr(4), bold)

        if not self.receive_utxo2:
            scr.addstr(waity2, waitx2 + 1, self._get_scroller())

            scr.timeout(1000)
            rpcw = self.config.rpc(self.cc_wallet)
            utxos = self.controller.get_utxos(rpcw)
            self.receive_utxo2 = utxos.get(self.toaddress1)

            if not self.receive_utxo2:
                return wait()

        self.new_step_line(
            f"Received amount of {self.receive_utxo2.amount} "
            f"({self.receive_utxo2.txid[:8]})",
            colr(5),
            bold,
            ypos=waity,
        )
        green_check(scr, testy, check_xpos)

        self.new_step_line("Your wallet is good to go! Press q to exit.", colr(5), bold)

        scr.move(self.height - 1, self.width - 1)
        # Refresh the screen
        scr.refresh()

        k = scr.getch()
        # Wait for next input
        return (k, GoSetup)

    def _get_scroller(self, do_spin=True):
        if not do_spin:
            return "   "
        modi = self.i % 3
        return {
            0: "[.  ]",
            1: "[ . ]",
            2: "[  .]",
        }[modi]


def _get_tx_info(rpcw, hex_val: str) -> t.List[str]:
    """Return a list of strings detailing the actions of a tx."""
    info = rpcw.decoderawtransaction(hex_val)
    outs: t.List[t.Tuple[str, Decimal]] = []
    out_strs = []

    for out in info["vout"]:
        addrs = ",".join(out["scriptPubKey"]["addresses"])
        outs.append((addrs, out["value"]))

        for o in outs:
            try:
                addr_info = rpcw.getaddressinfo(o[0])
            except Exception:
                # TODO handle this
                raise

            yours = addr_info["ismine"] or addr_info["iswatchonly"]
            yours_str = "  (your address)" if yours else ""
            out_strs.append(f"-> {o[0]}  ({o[1]} BTC){yours_str}")

    return out_strs


def draw_onboard(k: int) -> Action:
    return Quit


def green_check(scr, y, x):
    with attrs(scr, colr(5), bold):
        scr.addstr(y, x, "✔")


def box(scr, y, x):
    with attrs(scr, colr(2), bold):
        scr.addstr(y, x, "□")


def key_y(k: int):
    return k in {ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER}


GoHome = Action()
GoSetup = Action()
Quit = Action()


def draw_menu(scr, config, wallet_configs):
    # Clear and refresh the screen for a blank canvas
    scr.clear()
    scr.refresh()
    scr.scrollok(True)

    curses.start_color()
    curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    home = HomeScene()
    home.set_configs(scr, config, wallet_configs)

    setup = SetupScene()
    setup.set_configs(scr, config, wallet_configs)

    action = GoHome
    k = 0

    while action != Quit:
        # Initialization
        scr.clear()
        height, width = scr.getmaxyx()

        # FIXME
        scene = "h o m e"

        try:
            kstr = curses.keyname(k).decode()
        except ValueError:
            kstr = "???"

        statusbarstr = f"Press 'q' to exit | {scene} | last keypress: {kstr} ({k})"
        if k == -1:
            statusbarstr += " | waiting"
        # Render status bar
        with attrs(scr, colr(3)):
            try:
                scr.addstr(height - 1, 0, statusbarstr[:width])
                scr.addstr(
                    height - 1,
                    len(statusbarstr),
                    (" " * (width - len(statusbarstr) - 1))[:width],
                )
                # TODO
            except Exception:
                pass

        if action == GoHome:
            (k, action) = home.draw(k)
        elif action == GoSetup:
            (k, action) = setup.draw(k)

        if k == ord("q") or action == Quit:
            break


@contextlib.contextmanager
def attrs(scr, *attrs):
    for a in attrs:
        scr.attron(a)
    yield
    for a in attrs:
        scr.attroff(a)


def _pad_str(s: str, num: int) -> str:
    return (" " * num) + s + (" " * num)


def start_ui(config, wallet_configs):
    curses.wrapper(draw_menu, config, wallet_configs)
