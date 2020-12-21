"""
Basic encoding/cryptographic operations, mostly relating to xpub parsing.
"""
import hashlib
import io

# Much of this file was derived from code in buidl-python
# (https://github.com/buidl-bitcoin/buidl-python).


BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

MAINNET_XPRV = bytes.fromhex("0488ade4")
MAINNET_XPUB = bytes.fromhex("0488b21e")
MAINNET_YPRV = bytes.fromhex("049d7878")
MAINNET_YPUB = bytes.fromhex("049d7cb2")
MAINNET_ZPRV = bytes.fromhex("04b2430c")
MAINNET_ZPUB = bytes.fromhex("04b24746")
TESTNET_XPRV = bytes.fromhex("04358394")
TESTNET_XPUB = bytes.fromhex("043587cf")
TESTNET_YPRV = bytes.fromhex("044a4e28")
TESTNET_YPUB = bytes.fromhex("044a5262")
TESTNET_ZPRV = bytes.fromhex("045f18bc")
TESTNET_ZPUB = bytes.fromhex("045f1cf6")


def raw_decode_base58(s):
    num = 0
    # see how many leading 0's we are starting with
    prefix = b""
    for c in s:
        if num == 0 and c == "1":
            prefix += b"\x00"
        else:
            num = 58 * num + BASE58_ALPHABET.index(c)
    # put everything into base64
    byte_array = []
    while num > 0:
        byte_array.insert(0, num & 255)
        num >>= 8
    combined = prefix + bytes(byte_array)
    checksum = combined[-4:]
    if hash256(combined[:-4])[:4] != checksum:
        raise RuntimeError("bad address: {} {}".format(checksum, hash256(combined)[:4]))
    return combined[:-4]


def xpub_to_fp(xpub: str) -> str:
    raw = raw_decode_base58(xpub)

    if len(raw) != 78:
        raise ValueError("Not a proper extended key")

    version = raw[:4]

    if version not in (
        TESTNET_XPUB,
        TESTNET_YPUB,
        TESTNET_ZPUB,
        MAINNET_XPUB,
        MAINNET_YPUB,
        MAINNET_ZPUB,
    ):
        raise ValueError(f"not an xprv, yprv or zprv: {version}")

    return hash160(raw[-33:])[:4].hex()


def decode_base58(s):
    return raw_decode_base58(s)[1:]


def hash160(s):
    return hashlib.new("ripemd160", hashlib.sha256(s).digest()).digest()


def hash256(s):
    return hashlib.sha256(hashlib.sha256(s).digest()).digest()
