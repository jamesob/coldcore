from setuptools import setup
import os

here = os.path.abspath(os.path.dirname(__file__))

setup(
    name="coldcore",
    version="0.0.1",
    description="A small shim to connect Coldcards to Bitcoin Core",
    author="jamesob",
    author_email="hijamesob@pm.me",
    include_package_data=True,
    zip_safe=False,
    packages=["coldcore"],
    entry_points={
        "console_scripts": [
            "coldcore = coldcore.main:main",
        ],
    },
)
