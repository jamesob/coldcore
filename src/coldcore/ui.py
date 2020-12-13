import curses
import contextlib
import typing as t
import logging
import time
import subprocess
import http.client
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

        title = "\n".join((" " * start_x_title) + line for line in title.splitlines())
        start_x_subtitle = int((width // 2) - (len(subtitle) // 2) - len(subtitle) % 2)
        start_x_keystr = int((width // 2) - (len(keystr) // 2) - len(keystr) % 2)
        start_y = height // 4

        with attrs(scr, colr(2), bold):
            scr.addstr(start_y, width // 2, title)

        scr.addstr(start_y + title_height, start_x_subtitle, subtitle)
        scr.addstr(start_y + title_height + 2, start_x_title, "/ " * (title_len // 2))

        if wconfigs:
            scr.addstr(start_y + title_height + 4, start_x_keystr, keystr)

        def menu_option(idx: int, text: str, selected=False):
            half = width // 2

            start_str = f'{"":<6}{text:>20}{"":<6}'
            if selected:
                start_str = " -> " + start_str[4:]
            scr.addstr(start_y + title_height + 8 + idx, half, start_str)

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

        self.steps_xpos = 0
        self.steps_ypos = 0

    def new_step_line(self, msg, *attrs_, ypos: Op[int] = None) -> t.Tuple[int, int]:
        """Returns (y, x) of final cursor spot."""
        curr_ypos = ypos or self.steps_ypos
        with attrs(self.scr, *attrs_):
            self.scr.addstr(curr_ypos, self.steps_xpos, msg)

        if ypos is None:
            self.steps_ypos += 1
        return (curr_ypos, len(msg) + self.steps_xpos)

    def new_sec(self):
        self.steps_ypos += 1

    def draw(self, k: int) -> t.Tuple[int, Action]:
        scr = self.scr
        height, width = scr.getmaxyx()
        self.steps_ypos = 7

        scr.timeout(400)

        title = f"""
              __
.-----.-----.|  |_.--.--.-----.
|__ --|  -__||   _|  |  |  _  |
|_____|_____||____|_____|   __| {'=' * (width - 39)}
                        |__|
"""
        y_start = 0
        x_start = 4
        self.steps_xpos = x_start + 4
        check_xpos = self.steps_xpos - 3

        title = "\n".join((" " * x_start) + line for line in title.splitlines())

        with attrs(scr, colr(2), bold):
            scr.addstr(y_start, x_start, title)

        def wait():
            """Return this when we're waiting on a step."""
            return (scr.getch(), GoSetup)

        (core_ypos, _) = self.new_step_line("Searching for Bitcoin Core... ")
        box(scr, core_ypos, check_xpos)

        if not self.bitcoin_rpc:
            rpc = None
            try:
                for i in ("mainnet", "testnet3"):
                    try:
                        logger.info(f"trying RPC for {i}")
                        rpc = self.config.rpc(net_name=i)
                        rpc.help()
                    except:
                        pass
                    else:
                        break
                if not rpc:
                    raise ValueError("no rpc")

                self.bitcoin_rpc = rpc
                scr.refresh()
                time.sleep(0.6)
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

        chaininfo = self.bitcoin_rpc.getblockchaininfo()
        progress = chaininfo["verificationprogress"]

        if progress < 0.999:
            (chain_ypos, chain_xpos) = self.new_step_line(
                f"Initial block download progress: {progress * 100:.2f}%"
            )
            scr.timeout(4000)
            return wait()

        scr.timeout(400)
        self.new_step_line(f"Chain synced to height {chaininfo['blocks']}", colr(6))
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
        (scan_y, _) = self.new_step_line(
            "Scanning the UTXO set... (may take a few minutes)", colr(0)
        )

        if not self.core_scantxoutset:
            rpcw = self.config.rpc(self.cc_wallet, timeout=6000)
            self.core_scantxoutset = rpcw.scantxoutset(
                *self.cc_wallet.scantxoutset_args()
            )

        unspents = self.core_scantxoutset["unspents"]
        if self.core_scantxoutset["unspents"]:
            bal = sum([i["amount"] for i in unspents])
            min_height = min([i["height"] for i in unspents])
            self.new_step_line(
                f"Found a balance of {bal} BTC, earliest height: {min_height}",
                colr(5),
                ypos=scan_y,
            )
        else:
            self.new_step_line(
                f"Couldn't find a balance - new wallet eh?",
                colr(1),
                ypos=scan_y,
            )

        # Refresh the screen
        scr.refresh()

        k = scr.getch()
        # Wait for next input
        return (k, GoSetup)


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
            scr.addstr(height - 1, 0, statusbarstr)
            scr.addstr(
                height - 1, len(statusbarstr), " " * (width - len(statusbarstr) - 1)
            )

        if action == GoHome:
            (k, action) = home.draw(k)
        elif action == GoSetup:
            (k, action) = setup.draw(k)

        if k == ord("q") or action == Quit:
            break


def wait_for_quit():
    pass


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
