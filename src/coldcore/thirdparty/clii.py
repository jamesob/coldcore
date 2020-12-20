"""
clii

The easiest damned argparse wrapper there ever was.


Copyright 2020 James O'Beirne

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import sys
import argparse
import functools
import inspect
import typing as t
import os
import logging
from textwrap import dedent


logger = logging.getLogger("clii")
if os.environ.get("CLII_DEBUG"):
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())


class Arg:
    def __init__(
        self,
        name_or_flags: t.Union[str, t.Sequence[str]],
        type: object = str,
        help: str = "",
        default: object = inspect.Parameter.empty,
        is_kwarg: bool = False,
        is_vararg: bool = False,
        dest: t.Optional[str] = None,
    ):
        names: t.List[str] = (
            [name_or_flags] if isinstance(name_or_flags, str) else list(name_or_flags)
        )

        # Store original parameter name unmangled (e.g. no '-' for '_' sub).
        self.dest = dest or names[0]

        if is_kwarg:
            names = [n.replace("_", "-") for n in names]

        self.name = names[0]
        self.all_names = list(names)
        self.type = type
        self.default = default
        self.is_kwarg = is_kwarg
        self.is_vararg = is_vararg
        self.help = help

    @classmethod
    def from_parameter(cls, param: inspect.Parameter, help: str = "") -> "Arg":
        type = param.annotation
        arg = None

        def is_kwarg(p):
            return p.default != inspect.Parameter.empty

        if isinstance(type, cls):
            # User already specified an Arg, just use that.
            arg = type
            arg.is_kwarg = is_kwarg(param)
            arg.default = param.default
            arg.update_name(param.name)
            arg.dest = param.name
            return arg
        return cls(
            param.name,
            type=param.annotation,
            default=param.default,
            help=help,
            is_kwarg=is_kwarg(param),
            is_vararg=(param.kind == inspect.Parameter.VAR_POSITIONAL),
            dest=param.name,
        )

    @classmethod
    def from_func(cls, func: t.Callable) -> t.Sequence["Arg"]:
        # Ignore `**kwargs`; it can't be sensibly interpreted into flags
        params = [
            p for p in _get_func_params(func) if p.kind != inspect.Parameter.VAR_KEYWORD
        ]

        helps_from_doc = _get_helps_from_func(func, [p.name for p in params])

        return tuple(
            cls.from_parameter(param, helps_from_doc.get(param.name, ""))
            for param in _get_func_params(func)
            if
            # Ignore `**kwargs`; it can't be sensibly interpreted into flags
            param.kind != inspect.Parameter.VAR_KEYWORD
        )

    def add_to_parser(self, parser: argparse.ArgumentParser):
        kwargs = dict(default=self.default, type=self.type, help=self.arg_help)

        if self.is_kwarg:
            kwargs["dest"] = self.dest
        elif self.is_vararg:
            kwargs["nargs"] = "*"
            kwargs.pop("default", "")
            if kwargs.get("type") == inspect.Parameter.empty:
                kwargs.pop("type")

        if self.type == bool or any(self.default is i for i in [True, False]):
            kwargs["action"] = "store_false" if self.default else "store_true"
            kwargs.pop("type", "")

        logger.debug(f"Attaching argument: {self.names} -> {kwargs}")
        parser.add_argument(*self.names, **kwargs)  # type: ignore

    def update_name(self, name: str):
        if name not in self.all_names:
            self.all_names.insert(0, name)
        else:
            assert self.all_names[0] == name

        self.name = name

    @property
    def names(self) -> t.Tuple[str, ...]:
        if not self.is_kwarg:
            return (self.name,)

        assert all(i.startswith("-") for i in self.all_names[1:])
        assert self.name == self.all_names[0]
        return (f"--{self.name}",) + tuple(self.all_names[1:])

    @property
    def arg_help(self) -> str:
        out = self.help or ""
        if self.default is not inspect.Parameter.empty:
            if out:
                out += ". "
            out += f"default: {self.default}"
        return out


def _get_func_params(func) -> t.List[inspect.Parameter]:
    return list(inspect.signature(func).parameters.values())


def _get_helps_from_func(func, param_names) -> t.Dict[str, str]:
    if not func.__doc__:
        return {}

    helps_from_doc = {}

    for line in dedent(func.__doc__).splitlines():
        for p in param_names:
            patt = f"  {p}:"

            if patt in line:
                helps_from_doc[p] = line.split(patt)[-1].strip()

    return helps_from_doc


class App:
    def __init__(self, *args, **kwargs):
        self.parser = argparse.ArgumentParser(*args, **kwargs)
        self.subparsers = None
        self.args = argparse.Namespace()

    def add_arg(self, *args, **kwargs):
        self.parser.add_argument(*args, **kwargs)
        return self.parser

    add_argument = add_arg

    def main(self, fnc):
        self.parser.set_defaults(func=fnc)

        for arg in Arg.from_func(fnc):
            arg.add_to_parser(self.parser)

        if not self.parser.description:
            self.parser.description = fnc.__doc__

        @functools.wraps(fnc)
        def wrapper(*args, **kwargs):
            return fnc(*args, **kwargs)

        return wrapper

    def cmd(self, fnc) -> t.Callable:
        if not self.subparsers:
            self.subparsers = self.parser.add_subparsers()

        sub = self.subparsers.add_parser(
            fnc.__name__.replace("_", "-"), description=fnc.__doc__
        )
        logger.debug("Added subparser: %s", sub)

        for arg in Arg.from_func(fnc):
            arg.add_to_parser(sub)
            logger.debug("  Adding argument: %s", arg)

        sub.set_defaults(func=fnc)

        @functools.wraps(fnc)
        def wrapper(*args, **kwargs):
            return fnc(*args, **kwargs)

        return wrapper

    def parse_for_run(self) -> t.Tuple[t.Callable, t.Tuple[t.List, t.Dict]]:
        self.args = self.parser.parse_args()
        args = vars(self.args)
        logger.debug("Parsed args: %s", args)
        fnc = args.pop("func", None)

        if not fnc:
            self.parser.print_help()
            sys.exit(1)

        func_args = []
        func_kwargs = {}
        building_kwargs = False

        # Only pull in those parameters which `fnc` accepts, since the
        # global parser may have supplied more.
        for p in _get_func_params(fnc):
            if p.kind == inspect.Parameter.KEYWORD_ONLY:
                building_kwargs = True

            if building_kwargs:
                func_kwargs[p.name] = args[p.name]
            elif p.kind == inspect.Parameter.VAR_POSITIONAL:
                func_args.extend(args[p.name])
            else:
                func_args.append(args[p.name])

        return (fnc, (func_args, func_kwargs))

    def run(self):
        (fnc, (func_args, func_kwargs)) = self.parse_for_run()

        return fnc(*func_args, **func_kwargs)
