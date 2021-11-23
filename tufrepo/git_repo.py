# Copyright 2021 VMware, Inc.
# SPDX-License-Identifier: MIT OR Apache-2.0

# Git + filesystem based implementation of Repository. Invoked by the CLI.

import glob
import logging
import os
import subprocess

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Generator, List, Optional

from click.exceptions import ClickException
from securesystemslib.exceptions import StorageError
from tuf.api.metadata import Metadata, MetaFile, Signed
from tuf.api.serialization.json import JSONSerializer

from tufrepo import helpers
from tufrepo.librepo.repo import Repository

logger = logging.getLogger("tufrepo")

class GitRepository(Repository):
    """Manages loading, saving (signing) repository metadata in files stored in git"""

    @staticmethod
    def _git(command: List[str]):
        """Helper to run git commands in the repository git repo"""
        full_cmd = ["git"] + command
        proc = subprocess.run(full_cmd)
        return proc.returncode

    @staticmethod
    def _get_expiry(expiry_period: int) -> datetime:
        delta = timedelta(seconds=expiry_period)
        now = datetime.utcnow().replace(microsecond=0)
        return now + delta

    @staticmethod
    def _get_filename(role: str, version: Optional[int] = None):
        """Returns versioned filename"""
        if role == "timestamp":
            return f"{role}.json"
        else:
            if version is None:
                # Find largest version number in filenames
                filenames = glob.glob(f"*.{role}.json")
                versions = [int(name.split(".", 1)[0]) for name in filenames]
                try:
                    version = max(versions)
                except ValueError:
                    # No files found
                    version = 1

            return f"{version}.{role}.json"

    def _load(self, role:str) -> Metadata:
        fname = self._get_filename(role)
        try:
            return Metadata.from_file(fname)
        except StorageError as e:
            raise ClickException(f"Failed to open {fname}.") from e

    def _save(self, role: str, md: Metadata, clear_sigs: bool = True):
        self._sign_role(role, md, clear_sigs)

        fname = self._get_filename(role, md.signed.version)
        md.to_file(fname, JSONSerializer())

        self._git(["add", "--intent-to-add", self._get_filename(role, md.signed.version)])

    def init_role(self, role:str, period: int):
        md = helpers.init(role, self._get_expiry(period))
        md.signed.unrecognized_fields["x-tufrepo-expiry-period"] = period
        self._save(role, md)

    def snapshot(self):
        """Update snapshot and timestamp meta information

        This command only updates the meta information in snapshot/timestamp
        according to current filenames: it does not validate those files in any
        way. Run 'verify' after 'snapshot' to validate repository state.
        """

        # Find targets role name and newest version
        # NOTE: we trust the version in the filenames to be correct here
        targets_roles: Dict[str, MetaFile] = {}
        for filename in glob.glob("*.*.json"):
            version, keyname = filename[: -len(".json")].split(".")
            version = int(version)
            if keyname in ["root", "snapshot", "timestamp"]:
                continue
            keyname = f"{keyname}.json"
            
            curr_role = targets_roles.get(keyname)
            if not curr_role or version > curr_role.version:
                targets_roles[keyname] = MetaFile(version)

        removed = super().snapshot(targets_roles)

        for keyname, meta in removed.items():
            # delete the older file (if any): it is not part of snapshot
            try:
                os.remove(f"{meta.version}.{keyname}")
            except FileNotFoundError:
                pass

    @contextmanager
    def edit(self, role:str) -> Generator[Signed, None, None]:
        md = self._load(role)
        version = md.signed.version
        old_filename = self._get_filename(role, version)
        remove_old = False

        # Find out expiry and need for version bump
        try:
            period = md.signed.unrecognized_fields["x-tufrepo-expiry-period"]
        except KeyError:
            raise ClickException(
                "Expiry period not found in metadata: use 'set-expiry'"
            )
        expiry = self._get_expiry(period)

        diff_cmd = ["diff", "--exit-code", "--no-patch", "--", old_filename]
        if os.path.exists(old_filename) and self._git(diff_cmd) == 0:
            version += 1
            # only snapshots need deleting (targets are deleted in snapshot())
            if role == "snapshot":
                remove_old = True

        with super()._edit(role, expiry, version) as signed:
            yield signed

        if remove_old:
            os.remove(old_filename)
