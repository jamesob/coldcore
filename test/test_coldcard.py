import io

from coldcore import CCWallet, WpkhDescriptor


def test_parse_public():
    class MockRPC:
        def getdescriptorinfo(*args, **kwargs):
            return {"checksum": "deadbeef"}

    wall = CCWallet.from_io(io.StringIO(pub1), MockRPC())

    expected = {
        "bitcoind_json_url": None,
        "bitcoind_name": "coldcard-3d88d0cf",
        "loaded_from": None,
        "fingerprint": "3d88d0cf",
        "deriv_path": "/84h/0h",
        "xpub": "xpub6BUBVXTHPtiWZuJT7ZVArTEXi5FcGNX4d4TMLTuRSCcVEQ37BASyq17BoSBxwLgaVBvyR9GbtnVeKhAAwdmqHppzrukRk55XHgc32idASq2",
        "descriptors": [
            WpkhDescriptor(
                base="wpkh([3d88d0cf/84h/0h]xpub6BUBVXTHPtiWZuJT7ZVArTEXi5FcGNX4d4TMLTuRSCcVEQ37BASyq17BoSBxwLgaVBvyR9GbtnVeKhAAwdmqHppzrukRk55XHgc32idASq2/0/*)",
                checksum="deadbeef",
                is_change=False,
            ),
            WpkhDescriptor(
                base="wpkh([3d88d0cf/84h/0h]xpub6BUBVXTHPtiWZuJT7ZVArTEXi5FcGNX4d4TMLTuRSCcVEQ37BASyq17BoSBxwLgaVBvyR9GbtnVeKhAAwdmqHppzrukRk55XHgc32idASq2/1/*)",
                checksum="deadbeef",
                is_change=True,
            ),
        ],
        "name": "coldcard-3d88d0cf",
        "earliest_block": None,
    }

    assert wall.__dict__ == expected
    assert wall.name == "coldcard-3d88d0cf"
    assert wall.importmulti_args() == (
        [
            {
                "desc": "wpkh([3d88d0cf/84h/0h]xpub6BUBVXTHPtiWZuJT7ZVArTEXi5FcGNX4d4TMLTuRSCcVEQ37BASyq17BoSBxwLgaVBvyR9GbtnVeKhAAwdmqHppzrukRk55XHgc32idASq2/0/*)#deadbeef",
                "internal": False,
                "keypool": True,
                "range": [0, 3000],
                "timestamp": "now",
                "watchonly": True,
            },
            {
                "desc": "wpkh([3d88d0cf/84h/0h]xpub6BUBVXTHPtiWZuJT7ZVArTEXi5FcGNX4d4TMLTuRSCcVEQ37BASyq17BoSBxwLgaVBvyR9GbtnVeKhAAwdmqHppzrukRk55XHgc32idASq2/1/*)#deadbeef",
                "internal": True,
                "keypool": True,
                "range": [0, 3000],
                "timestamp": "now",
                "watchonly": True,
            },
        ],
    )

    wall_testnet = CCWallet.from_io(io.StringIO(testnet1), MockRPC())

    assert wall_testnet.__dict__ == {
        "fingerprint": "f0ccde95",
        "bitcoind_name": "coldcard-f0ccde95",
        "loaded_from": None,
        "deriv_path": "/84h/1h/0h",
        "xpub": "tpubDCmmTK7n4vhofN8wuc5ioZcm9egBgwTRN7BRbpg8AHdLqA3TkyjkuvFbrymQBDHBNEvop6KFqHH1SCP1Qe9u55U2fzpvg9jLqhEPEHuTAt4",
        "descriptors": [
            WpkhDescriptor(
                base="wpkh([f0ccde95/84h/1h/0h]tpubDCmmTK7n4vhofN8wuc5ioZcm9egBgwTRN7BRbpg8AHdLqA3TkyjkuvFbrymQBDHBNEvop6KFqHH1SCP1Qe9u55U2fzpvg9jLqhEPEHuTAt4/0/*)",
                checksum="deadbeef",
                is_change=False,
            ),
            WpkhDescriptor(
                base="wpkh([f0ccde95/84h/1h/0h]tpubDCmmTK7n4vhofN8wuc5ioZcm9egBgwTRN7BRbpg8AHdLqA3TkyjkuvFbrymQBDHBNEvop6KFqHH1SCP1Qe9u55U2fzpvg9jLqhEPEHuTAt4/1/*)",
                checksum="deadbeef",
                is_change=True,
            ),
        ],
        "earliest_block": None,
        "bitcoind_json_url": None,
        "name": "coldcard-f0ccde95",
    }


# noqa: E501
pub1 = """
# Coldcard Wallet Summary File

## Wallet operates on blockchain: Bitcoin

For BIP44, this is coin_type '0', and internally we use symbol BTC for this blockchain.

## Top-level, 'master' extended public key ('m/'):

xpub661MyMwAqRbcGQU2MzQdLtxKvfa9shyo1vUGkxETFtDNGjggQMNMd5rTZfbKR25yCXHgtpwwko4Cyq1PkzLoEGRSmNy5GnnhCkWERN1wJSy

Derived public keys, as may be needed for different systems:


## For Bitcoin Core: m/{account}'/{change}'/{idx}'

m => xpub661MyMwAqRbcGQU2MzQdLtxKvfa9shyo1vUGkxETFtDNGjggQMNMd5rTZfbKR25yCXHgtpwwko4Cyq1PkzLoEGRSmNy5GnnhCkWERN1wJSy

... first 5 receive addresses (account=0, change=0):

m/0'/0'/0' => 1AaTq7W3Mw8J4UGpKL1Sc4DwWpNQSBgeHa
m/0'/0'/1' => 1GRDRoXkjPue2SPXvL8XZz5paK2Te4tbxZ
m/0'/0'/2' => 1Gxwx9pxvsmQCTf3Yx2Yo2jfSqjeHTgqJA
m/0'/0'/3' => 13ECwnbfj99my2edurXyzVtGW8NYGHq7u1
m/0'/0'/4' => 1D8KQ8Yctm4WesGsviQ8ZWApSbh7PAnLqy


## For Bitcoin Core (Segregated Witness, P2PKH): m/{account}'/{change}'/{idx}'

m => xpub661MyMwAqRbcGQU2MzQdLtxKvfa9shyo1vUGkxETFtDNGjggQMNMd5rTZfbKR25yCXHgtpwwko4Cyq1PkzLoEGRSmNy5GnnhCkWERN1wJSy
# SLIP-132 style
m => zpub6jftahH18ngZxzrG2hysm59LGbs3kwxnr9WiKk2E1ty8NwK8ufhUsDAjc5WVQqPp1oXJPn94g7mJkQEXCPAppjneW4MvScRfkCdXCXk1zgB

... first 5 receive addresses (account=0, change=0):

m/0'/0'/0' => bc1qdyx5z3p6nlxrjfay7mhefx8t4jscqu6sueg0vu
m/0'/0'/1' => bc1q4y0ruupprurvl9umalmt0u9ztju0qxfqfrqwhw
m/0'/0'/2' => bc1q4u029f45f3xegw2z72kmd4xcfl8dgsvg58u7xn
m/0'/0'/3' => bc1qrph6zs0yzrxg5j52qzp4s9njmp3lqj88tdv7ur
m/0'/0'/4' => bc1qs5pu0x8aqjslxvng7hq4w743gysgrnspxnagtz


## For Electrum (not BIP44): m/{change}/{idx}

m => xpub661MyMwAqRbcGQU2MzQdLtxKvfa9shyo1vUGkxETFtDNGjggQMNMd5rTZfbKR25yCXHgtpwwko4Cyq1PkzLoEGRSmNy5GnnhCkWERN1wJSy

... first 5 receive addresses (account=0, change=0):

m/0/0 => 16PYSMXY2BatS8FzbzwrAqM1HrHhxPzz2A
m/0/1 => 1JccZ1v4rZ3WhU9JDSVv1z1GwgwYQpJr7m
m/0/2 => 1MJ5TicEUw169T8qp6E2QUuLkeECz2QD27
m/0/3 => 1J3f5S8v6VVHqHCfs7ECeVhvAbpV6EUKna
m/0/4 => 1C8A19VJL9NPfKNp6TiebQTJqtVNwbJ1hp


## For BIP44 / Electrum: m/44'/0'/{account}'/{change}/{idx}

m/44'/0' => xpub6AuabxJxEnAJbc8iBE2B5n7hxYAZC5xLjpG7oY1kyhMfz5mN13wLRaGPnCyvLo4Ec5aRSa6ZeMPHMUEABpdKxtcPymJpDG5KPEsLGTApGye

... first 5 receive addresses (account=0, change=0):

m/44'/0'/0'/0/0 => 1NDKGzwrhz8n7euEapPRZkktiyXBEXFyKf
m/44'/0'/0'/0/1 => 1NK9ir2VTiYfVGvSKUwftqy1HQWJPwtSrC
m/44'/0'/0'/0/2 => 1L8cB6b3WEzkCqTFGSWWyEKZMqiytP8TTX
m/44'/0'/0'/0/3 => 15grLkNbrKakMFE2eJWXa6hQNJRzswvsK4
m/44'/0'/0'/0/4 => 16714S67jGeL9zp6qQjLJd9WpsswoTVgY7


## For BIP49 (P2WPKH-nested-in-P2SH): m/49'/0'/{account}'/{change}/{idx}

m/49'/0' => xpub6ApwLnWVoU6m4aGMh1kVbwA8CACF2m31sGkJbSx15KWjifbBnE1UHjvToBJZpqDmcMD859Si6DrRPace7Q4TBMiGQwvHttjJQiwB7TL6j8H
# SLIP-132 style
m/49'/0' => ypub6VfCeTBQx9eEusTUXNY7p2FdN8LgyP2WnPGXNqqtTKtcmmQR2tB2uoabpPG9pjsh1zKvpd3GYtCyGsECq6UTybPsHHciUoYngSzpW25khLg

... first 5 receive addresses (account=0, change=0):

m/49'/0'/0'/0/0 => 3KfeHRpD4VbPnm928NVx5QBsZ4Si9L3TJH
m/49'/0'/0'/0/1 => 3Fsj1s12r12ykx7cQ6VPzXLYe2kHEHP1zk
m/49'/0'/0'/0/2 => 35Xezi189cXAx3DZ9PLUwzhVqejB22GSKc
m/49'/0'/0'/0/3 => 3BD6i8i6jYg83CCNsEo4b8hruECmFeuPNd
m/49'/0'/0'/0/4 => 3J3pVvhYt4LmGGRsTfkrnWukLg2yXd45oQ


## For BIP84 (Native Segwit P2PKH): m/84'/0'/{account}'/{change}/{idx}

m/84'/0' => xpub6BUBVXTHPtiWZuJT7ZVArTEXi5FcGNX4d4TMLTuRSCcVEQ37BASyq17BoSBxwLgaVBvyR9GbtnVeKhAAwdmqHppzrukRk55XHgc32idASq2
# SLIP-132 style
m/84'/0' => zpub6q8i6ro7hFoUGVggnH4RGdRY41YW9cW4THVnuFhCCDNFLbfZgUn758RTqr78w9zRJUAav6Tip7Ck6GPJP2brtJCCbb9GutiVq8jKoqNszsS

... first 5 receive addresses (account=0, change=0):

m/84'/0'/0'/0/0 => bc1qkwyhuqeu37f7erej85fwwtn33cmupnmra4rf2k
m/84'/0'/0'/0/1 => bc1qmng3kwg97p0emk8p8w4faym8y9w8zqeld90k2a
m/84'/0'/0'/0/2 => bc1qgaqzjdnztrle7v4qg3yvnwnu5rndpkdn3gftxm
m/84'/0'/0'/0/3 => bc1qc703cjt0jvx2adsjfhg2dcfp8k34j76xymkqdl
m/84'/0'/0'/0/4 => bc1qk3ru377gs5wj0e8psyse2jrwxn5jym3kx8ufla
    """

testnet1 = """
# Coldcard Wallet Summary File
## For wallet with master key fingerprint: F0CCDE95

Wallet operates on blockchain: Bitcoin Testnet

For BIP44, this is coin_type '1', and internally we use
symbol XTN for this blockchain.

## IMPORTANT WARNING

Do **not** deposit to any address in this file unless you have a working
wallet system that is ready to handle the funds at that address!

## Top-level, 'master' extended public key ('m/'):

tpubD6NzVbkrYhZ4WTS6a1w2bMvnQLu5fFx2WFQYYshfaybZ38hhB1R4pEpcqtR6XQnGNqnZqdxzM2Zu9voRejsUFXGrUP2dDmFdQM6VH1dxjxy

What follows are derived public keys and payment addresses, as may
be needed for different systems.


## For Electrum (not BIP44): m/{change}/{idx}

First 5 receive addresses (account=0, change=0):

m => tpubD6NzVbkrYhZ4WTS6a1w2bMvnQLu5fFx2WFQYYshfaybZ38hhB1R4pEpcqtR6XQnGNqnZqdxzM2Zu9voRejsUFXGrUP2dDmFdQM6VH1dxjxy
m/0/0 => mtdRRTkhiR5F36qQEKrhEqiwgDZJTAo4KL
m/0/1 => mu99LL68Qjg836KStipjZhtiWrCUs5F4zt
m/0/2 => mmvRCw8ViHxXKLPT9E28EjM5eHUKg7X7fo
m/0/3 => mmjrC3Zx9SsJULVgeDpQ8S5ip7aRHa6TdD
m/0/4 => mqdhidRoF7UK7rSWzzpA2jw2qKA6JNtXP7


## For BIP44 / Electrum: m/44'/1'/{account}'/{change}/{idx}

First 5 receive addresses (account=0, change=0):

m/44'/1'/0' => tpubDDm5E3x41M3Atm6EdxuiDHNUPHFHFDbNuVX3cDeHiMsDmXpUA8WgJX3rmJ5yz6K8X7oRUAUsHnK9iKXEiSw5mfTmHG1J6886gpkLrRC7Jyr
m/44'/1'/0'/0/0 => mqX6Huj8JNKCzmvGEWkZANQn9wKHAS1fdj
m/44'/1'/0'/0/1 => mviw38chcm8rzBs5TEmgEQnkBqutcrdf9X
m/44'/1'/0'/0/2 => mukeH2vf4ZXVJ2xbLRsMQMda9x5E6FsauZ
m/44'/1'/0'/0/3 => mguijy6L91dcSAzSZCypxJaWHP9EKq6o6R
m/44'/1'/0'/0/4 => mp8XQPxD9wHroMWQwEFuNhQWcCRXriSB7s


## For BIP49 (P2WPKH-nested-in-P2SH): m/49'/1'/{account}'/{change}/{idx}

First 5 receive addresses (account=0, change=0):

m/49'/1'/0' => tpubDDeZsDGecR2h5BR1ySLrpNFzq83ph4oCt9cBzLiKPrCzVqHEXjMmLH2kUqocksLmFVkF9pqMbtrb2Hsm7M9MtJSawkV2mtjjE1ZRdU7iVK4
m/49'/1'/0' => upub5En9RySDT6SoFVep2AztzBe7z6WpspKebBTEHbyWuvKTbFAqhY1zKePWBBr5EeRmEfrvHpXogoxtgFYTZQ45c9wVH8eTLdd2psn5himfpfk   ##SLIP-132##
m/49'/1'/0'/0/0 => 2N4d2KghiPmGmvLn9wpHCLm8hyWaFY2cezA
m/49'/1'/0'/0/1 => 2NDFVTNLShuVYN6hmQTCxE9fBeCJqvXYV6t
m/49'/1'/0'/0/2 => 2NDqbEmmGKhP8AWjRznj5fZzNe3Zqvdx3MF
m/49'/1'/0'/0/3 => 2NGAP5QVwGLZGMZvkH2AJyisqU46EpqDWFP
m/49'/1'/0'/0/4 => 2N4f3qK2dNNuTRyemCDs8Qhe83jZyk1uBbp


## For BIP84 (Native Segwit P2WPKH): m/84'/1'/{account}'/{change}/{idx}

First 5 receive addresses (account=0, change=0):

m/84'/1'/0' => tpubDCmmTK7n4vhofN8wuc5ioZcm9egBgwTRN7BRbpg8AHdLqA3TkyjkuvFbrymQBDHBNEvop6KFqHH1SCP1Qe9u55U2fzpvg9jLqhEPEHuTAt4
m/84'/1'/0' => vpub5YjcKjxG4HfPgyZrnhXPBU6PUbHdpJyMzFYggUqD4N7gyfkJBSZYXMGVaXmSeu26m4AHhZcGNrjrySfGaPUdbAeXsigmpoS8iHWgh9D1nB6   ##SLIP-132##
m/84'/1'/0'/0/0 => tb1qm58ffex57zsacpdaar996xepcp5egmh2h8p2tr
m/84'/1'/0'/0/1 => tb1q4zsq0s7kp52vnshm73ff5kp6p70e0s8y069usu
m/84'/1'/0'/0/2 => tb1qauf8awghs8pcv3cu4us43uzuf9jzk63kdp457e
m/84'/1'/0'/0/3 => tb1q5rdc078nn7vfu6fkxexwcfarm4mwwrt4l6jhte
m/84'/1'/0'/0/4 => tb1q7m5wwdyhewcagz7lz3730pqj455fw45k4r740r

"""
