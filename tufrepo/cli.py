# Copyright 2021 VMware, Inc.
# SPDX-License-Identifier: MIT OR Apache-2.0

import click
import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Tuple

from tuf.api.metadata import(
    DelegatedRole,
    Delegations,
    SuccinctRoles,
    Targets
)

from tufrepo import helpers
from tufrepo import verifier
from tufrepo.librepo.keys import Keyring
from tufrepo.git_repo import GitRepository
from tufrepo.keys_impl import EnvVarKeyring, InsecureFileKeyring, PrivateKey

logger = logging.getLogger("tufrepo")

@dataclass
class AppData:
    keyring: Keyring
    role: str = None
    repo: GitRepository = None

    def __init__(self, keyring: Keyring) -> None:
        self.keyring = keyring
        self.repo = GitRepository(self.keyring)


class Context(click.Context):
    """click.Context where obj type is Appdata"""
    def __init__(self):
        super().__init__()
        self.obj: AppData


# -------------------------------- cli commands --------------------------------


@click.group()
@click.pass_context
@click.option("-v", "--verbose", count=True, default=0)
@click.option("--keyring", type=click.Choice(["file", "env"]), default="file")
def cli(ctx: Context, verbose: int, keyring: str):
    """Edit and sign TUF repository metadata

    This tool expects to be run in a directory with TUF metadata that is within
    a git repository.

    By default private keys are read in plaintext fom privkeys.json: this can
    be changed with "--keyring" to use environment variables named
    TUF_REPO_PRIVATE_KEY_<keyid> (useful in automation, like running in CI).
    """

    logging.basicConfig(format="%(levelname)s:%(message)s")
    logger.setLevel(max(1, 10 * (5 - verbose)))

    if keyring == "env":
        ctx.obj = AppData(EnvVarKeyring())
    else:
        ctx.obj = AppData(InsecureFileKeyring())

@cli.command()
@click.pass_context
def init(ctx: Context):
    """Initialize a repository

    All metadata will be assigned expiry period of 365 days: use
    'edit ROLE set-expiry' to change. A key will be generated for each role
    and stored in the keyring."""
    # Use expiry period of 1 year for everything
    period = int(timedelta(days=365).total_seconds())

    ctx.obj.repo.init_role("root", period)

    with ctx.obj.repo.edit("root") as root:
        for role in ["root", "timestamp", "snapshot", "targets"]:
            key: PrivateKey = ctx.obj.keyring.generate_key()
            root.add_key(key.public, role)
            ctx.obj.keyring.store_key(role, key)

    ctx.obj.repo.init_role("timestamp", period)
    ctx.obj.repo.init_role("snapshot", period)
    ctx.obj.repo.init_role("targets", period)
    ctx.obj.repo.snapshot()

@cli.command()
@click.pass_context
@click.argument("roles", nargs=-1)
def sign(ctx: Context, roles: Tuple[str]):
    """Sign the given roles, using all usable keys in keyring"""
    for role in roles:
        ctx.obj.repo.sign(role)

@cli.command()
@click.pass_context
@click.option("--root-hash")
def verify(ctx: Context, root_hash: Optional[str] = None):
    """"""
    verifier.verify_repo(root_hash)
    print(f"Keyring contains keys for [{', '.join(ctx.obj.keyring.keys())}].")


@cli.command()
@click.pass_context
def snapshot(ctx: Context):
    """"""
    ctx.obj.repo.snapshot()


# ------------------------------- edit commands --------------------------------


@cli.group()
@click.pass_context
@click.argument("role")
def edit(ctx: Context, role: str):
    """Edit metadata for ROLE using the sub-commands."""
    ctx.obj.role = role

@edit.command()
@click.pass_context
def touch(ctx: Context):
    """Mark ROLE as modified to force a new version"""
    with ctx.obj.repo.edit(ctx.obj.role):
        pass

@edit.command()
@click.pass_context
@click.option(
    "--expiry",
    help="expiry value and unit",
    default=(1, "days"),
    type=(int, click.Choice(["minutes", "days", "weeks"], case_sensitive=False)),
)
def init(ctx: Context, expiry: Tuple[int, str]):
    """Create new metadata for ROLE. Example:

    tufrepo edit root init --expiry 52 weeks"""
    delta = timedelta(**{expiry[1]: expiry[0]})
    period = int(delta.total_seconds())
    ctx.obj.repo.init_role(ctx.obj.role, period)


@edit.command()
@click.pass_context
@click.argument("delegate")
@click.argument("threshold", type=int)
def set_threshold(ctx: Context, delegate: str, threshold: int):
    """Set the threshold of delegated role DELEGATE."""
    with ctx.obj.repo.edit(ctx.obj.role) as signed:
        helpers.set_threshold(signed, delegate, threshold)


@edit.command()
@click.pass_context
@click.argument(
    "expiry",
    type=(int, click.Choice(["minutes", "days", "weeks"], case_sensitive=False)),
)
def set_expiry(ctx: Context, expiry: Tuple[int, str]):
    """Set expiry period for the role. Example:

    tufrepo edit root set-expiry 52 weeks"""
    delta = timedelta(**{expiry[1]: expiry[0]})
    period = int(delta.total_seconds())

    with ctx.obj.repo.edit(ctx.obj.role) as signed:
        # This should maybe be a repo feature? argument to edit?
        signed.unrecognized_fields["x-tufrepo-expiry-period"] = period


@edit.command()
@click.pass_context
@click.argument("delegate")
def add_key(ctx: Context, delegate: str):
    """Add new signing key for delegated role DELEGATE

    The private key secret will be written to privkeys.json."""
    delegator = ctx.obj.role
    keyring: InsecureFileKeyring = ctx.obj.keyring
    key = keyring.generate_key()

    with ctx.obj.repo.edit(delegator) as signed:
        helpers.add_key(signed, delegator, delegate, key.public)
    keyring.store_key(delegate, key)


@edit.command()
@click.pass_context
@click.argument("delegate")
@click.argument("keyid")
def remove_key(ctx: Context, delegate: str, keyid: str):
    """Remove signing key from delegated role DELEGATE"""
    delegator = ctx.obj.role

    with ctx.obj.repo.edit(delegator) as signed:
        helpers.remove_key(signed, delegator, delegate, keyid)


@edit.command()
@click.pass_context
@click.option("--target-in-repo/--no-target-in-repo", default=True)
@click.argument("target-path")
@click.argument("local-file")
def add_target(
    ctx: Context,
    target_in_repo: bool,
    target_path: str,
    local_file: str,
):
    """Add a target to a Targets metadata role"""
    ctx.obj.repo.add_target(
        ctx.obj.role, target_in_repo, target_path, local_file
    )


@edit.command()
@click.pass_context
@click.argument("target-path")
def remove_target(ctx: Context, target_path: str):
    """Remove TARGET from a Targets role ROLE"""

    targets: Targets
    with ctx.obj.repo.edit(ctx.obj.role) as targets:
        del targets.targets[target_path]
    print(f"Removed {target_path} from {ctx.obj.role}.")
    print("Actual target files have not been removed")


@edit.command()
@click.pass_context
@click.argument("delegate")
@click.option("--terminating/--non-terminating", default=False)
@click.option("--path", "paths", multiple=True)
@click.option("--hash-prefix", "hash_prefixes", multiple=True)
def add_delegation(
    ctx: Context,
    delegate: str,
    terminating: bool,
    paths: Tuple[str],
    hash_prefixes: Tuple[str],
):
    """Delegate from ROLE to DELEGATE"""

    _paths = list(paths) if paths else None
    _prefixes = list(hash_prefixes) if hash_prefixes else None

    targets: Targets
    with ctx.obj.repo.edit(ctx.obj.role) as targets:
        if targets.delegations is None:
            targets.delegations = Delegations({}, {})

        role = DelegatedRole(delegate, [], 1, terminating, _paths, _prefixes)
        targets.delegations.roles[role.name] = role

@edit.command()
@click.pass_context
@click.argument("number", type=int)
@click.option(
    "--name-prefix",
    help="Name prefix for all bins.",
    type=str,
    default="bin",
    show_default=True
)
def add_succinct_delegation(
    ctx: Context,
    number: int,
    name_prefix: str,
):
    """Add succinct hash bin delegation to a ROLE representing NUMBER of bins.

    NUMBER must be a power of 2, otherwise, an error will be raised.

    Note: if ROLE contains other role delegations they will be overwritten.
    """
    if number < 2:
        raise ValueError("Number must be at least 2")
    if number % 2 != 0:
        raise ValueError("NUMBER must be a power of 2")
    # Calculate bit_length based on the number of the given succinct_bin_num.
    bit_length = int(math.log2(number))
    targets: Targets
    with ctx.obj.repo.edit(ctx.obj.role) as targets:
        succinct_roles =  SuccinctRoles([], 1, bit_length, name_prefix)
        targets.delegations = Delegations({}, None, succinct_roles)


@edit.command()
@click.pass_context
@click.argument("delegate")
def remove_delegation(
    ctx: Context,
    delegate: str,
):
    """Remove DELEGATE from ROLE"""
    tar: Targets
    with ctx.obj.repo.edit(ctx.obj.role) as tar:
        if tar.delegations is not None and tar.delegations.roles is not None:
            del tar.delegations.roles[delegate]
