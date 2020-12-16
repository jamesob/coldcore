# Copyright (C) 2007 Jan-Klaas Kollhof
# Copyright (C) 2011-2018 The python-bitcoinlib developers
# Copyright (C) 2020 James O'Beirne
#
# This section is part of python-bitcoinlib.
#
# It is subject to the license terms in the LICENSE file found in the top-level
# directory of the python-bitcoinlib distribution.
#
# No part of python-bitcoinlib, including this section, may be copied, modified,
# propagated, or distributed except according to the terms contained in the
# LICENSE file.

import logging
import os
import base64
import http.client as httplib
import json
import platform
import urllib.parse as urlparse
import re
import time
import http.client
from typing import IO, Optional as Op
from decimal import Decimal

DEFAULT_USER_AGENT = "AuthServiceProxy/0.1"
DEFAULT_HTTP_TIMEOUT = 30


logger = logging.getLogger("rpc")
logger.setLevel(logging.DEBUG)
# logger.addHandler(logging.StreamHandler())


class JSONRPCError(Exception):
    """JSON-RPC protocol error base class
    Subclasses of this class also exist for specific types of errors; the set
    of all subclasses is by no means complete.
    """

    def __init__(self, rpc_error):
        super(JSONRPCError, self).__init__(
            "msg: %r  code: %r" % (rpc_error["message"], rpc_error["code"])
        )
        self.error = rpc_error


class BaseProxy(object):
    """Base JSON-RPC proxy class. Contains only private methods; do not use
    directly."""

    def __init__(
        self,
        service_url=None,
        service_port=None,
        btc_conf_file=None,
        net_name=None,
        timeout=DEFAULT_HTTP_TIMEOUT,
        connection=None,
        debug_stream: Op[IO] = None,
        wallet_name=None,
    ):

        # Create a dummy connection early on so if __init__() fails prior to
        # __conn being created __del__() can detect the condition and handle it
        # correctly.
        self.debug_stream = debug_stream
        authpair = None
        net_name = net_name or "mainnet"
        self.timeout = timeout
        self.net_name = net_name

        if service_url is None:
            # Figure out the path to the bitcoin.conf file
            if btc_conf_file is None:
                if platform.system() == "Darwin":
                    btc_conf_file = os.path.expanduser(
                        "~/Library/Application Support/Bitcoin/"
                    )
                elif platform.system() == "Windows":
                    btc_conf_file = os.path.join(os.environ["APPDATA"], "Bitcoin")
                else:
                    btc_conf_file = os.path.expanduser("~/.bitcoin")
                btc_conf_file = os.path.join(btc_conf_file, "bitcoin.conf")

            # Bitcoin Core accepts empty rpcuser, not specified in btc_conf_file
            conf = {"rpcuser": ""}

            # Extract contents of bitcoin.conf to build service_url
            try:
                with open(btc_conf_file, "r") as fd:
                    for line in fd.readlines():
                        if "#" in line:
                            line = line[: line.index("#")]
                        if "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        conf[k.strip()] = v.strip()

            # Treat a missing bitcoin.conf as though it were empty
            except FileNotFoundError:
                pass

            if service_port is None:
                service_port = {
                    "mainnet": 8332,
                }.get(net_name, 18332)

            conf["rpcport"] = int(conf.get("rpcport", service_port))
            conf["rpchost"] = conf.get("rpcconnect", "localhost")

            service_url = "%s://%s:%d" % ("http", conf["rpchost"], conf["rpcport"])

            cookie_dir = conf.get("datadir", os.path.dirname(btc_conf_file))
            if net_name != "mainnet":
                cookie_dir = os.path.join(cookie_dir, net_name)
            cookie_file = os.path.join(cookie_dir, ".cookie")
            try:
                with open(cookie_file, "r") as fd:
                    authpair = fd.read()
            except IOError as err:
                if "rpcpassword" in conf:
                    authpair = "%s:%s" % (conf["rpcuser"], conf["rpcpassword"])

                else:
                    raise ValueError(
                        "Cookie file unusable (%s) and rpcpassword not specified "
                        "in the configuration file: %r" % (err, btc_conf_file)
                    )

        else:
            url = urlparse.urlparse(service_url)
            authpair = "%s:%s" % (url.username, url.password)

        if wallet_name:
            service_url += f"/wallet/{wallet_name}"

        logger.info(f"SERVICE URL: {service_url}")
        self.url = service_url

        # Credential redacted
        self.public_url = re.sub(r":[^/]+@", ":***@", self.url, 1)
        self._parsed_url = urlparse.urlparse(service_url)

        logger.info(f"Initializing RPC client at {self.public_url}")

        if self._parsed_url.scheme not in ("http",):
            raise ValueError("Unsupported URL scheme %r" % self._parsed_url.scheme)

        self.__id_count = 0

        self.__auth_header = None
        if authpair:
            self.__auth_header = b"Basic " + base64.b64encode(authpair.encode("utf8"))

    def _getconn(self):
        if self._parsed_url.port is None:
            port = httplib.HTTP_PORT
        else:
            port = self._parsed_url.port
        return httplib.HTTPConnection(
            self._parsed_url.hostname, port=port, timeout=self.timeout
        )

    def _call(self, service_name, *args):
        self.__id_count += 1

        postdata = json.dumps(
            {
                "version": "1.1",
                "method": service_name,
                "params": args,
                "id": self.__id_count,
            }
        )

        logger.debug(f"[{self.public_url}] calling %s%s", service_name, args)

        headers = {
            "Host": self._parsed_url.hostname,
            "User-Agent": DEFAULT_USER_AGENT,
            "Content-type": "application/json",
        }

        if self.__auth_header is not None:
            headers["Authorization"] = self.__auth_header

        path = self._parsed_url.path
        tries = 5
        backoff = 0.3
        while tries:
            try:
                conn = self._getconn()
                conn.request("POST", path, postdata, headers)
            except (BlockingIOError, http.client.CannotSendRequest):
                logger.exception(
                    f"hit request error: {path}, {postdata}, {self._parsed_url}"
                )
                tries -= 1
                if not tries:
                    raise
                time.sleep(backoff)
                backoff *= 2
            else:
                break

        response = self._get_response(conn)
        err = response.get("error")
        if err is not None:
            if isinstance(err, dict):
                raise JSONRPCError(
                    {
                        "code": err.get("code", -345),
                        "message": err.get("message", "error message not specified"),
                    }
                )
            raise JSONRPCError({"code": -344, "message": str(err)})
        elif "result" not in response:
            raise JSONRPCError({"code": -343, "message": "missing JSON-RPC result"})
        else:
            return response["result"]

    def _get_response(self, conn):
        http_response = conn.getresponse()
        if http_response is None:
            raise JSONRPCError(
                {"code": -342, "message": "missing HTTP response from server"}
            )

        rdata = http_response.read().decode("utf8")
        try:
            return json.loads(rdata, parse_float=Decimal)
        except Exception:
            raise JSONRPCError(
                {
                    "code": -342,
                    "message": (
                        "non-JSON HTTP response with '%i %s' from server: '%.20s%s'"
                        % (
                            http_response.status,
                            http_response.reason,
                            rdata,
                            "..." if len(rdata) > 20 else "",
                        )
                    ),
                }
            )


class RawProxy(BaseProxy):
    """Low-level proxy to a bitcoin JSON-RPC service
    Unlike ``Proxy``, no conversion is done besides parsing JSON. As far as
    Python is concerned, you can call any method; ``JSONRPCError`` will be
    raised if the server does not recognize it.
    """

    def __init__(
        self,
        service_url=None,
        service_port=None,
        btc_conf_file=None,
        timeout=DEFAULT_HTTP_TIMEOUT,
        **kwargs,
    ):
        super(RawProxy, self).__init__(
            service_url=service_url,
            service_port=service_port,
            btc_conf_file=btc_conf_file,
            timeout=timeout,
            **kwargs,
        )

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            # Prevent RPC calls for non-existing python internal attribute
            # access. If someone tries to get an internal attribute
            # of RawProxy instance, and the instance does not have this
            # attribute, we do not want the bogus RPC call to happen.
            raise AttributeError

        # Create a callable to do the actual call
        def _call_wrapper(*args):
            return self._call(name, *args)

        # Make debuggers show <function bitcoin.rpc.name> rather than <function
        # bitcoin.rpc.<lambda>>
        _call_wrapper.__name__ = name
        return _call_wrapper


BitcoinRPC = RawProxy
