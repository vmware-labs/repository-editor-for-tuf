# Copyright 2021 VMware, Inc.
# SPDX-License-Identifier: MIT OR Apache-2.0

import abc
import glob
import json
import logging
import os

from securesystemslib.keys import generate_ed25519_key
from tuf.api.metadata import (
    Key,
    Metadata,
    Root,
    Targets,
)
from typing import DefaultDict, Dict, Set

from tufrepo.librepo.keys import PrivateKey

logger = logging.getLogger("tufrepo")


class Keyring(DefaultDict[str, Set[PrivateKey]], metaclass=abc.ABCMeta):
    """A base class for the private keyring management implementations."""

    def __init__(self):
        super().__init__(set)
        self._load_private_keys()

    @abc.abstractmethod
    def _load_key(self, rolename: str, key: Key) -> None:
        """Load the private key of a given role and add it to the "key" object."""
        raise NotImplementedError

    def _load_private_keys(self):
        """Loads secrets for all delegating roles in this repository by using
        self._load_key(). This currently loads all delegating metadata to
        findthe public keys."""

        # find all delegating roles in the repository
        roles: Dict[str, int] = {}
        for filename in glob.glob("*.*.json"):
            ver_str, delegating_role = filename[: -len(".json")].split(".")
            if delegating_role not in ["timestamp", "snapshot"]:
                roles[delegating_role] = max(
                    int(ver_str), roles.get(delegating_role, 0)
                )

        # find all signing keys for all roles
        for delegating_role, version in roles.items():
            md = Metadata.from_file(f"{version}.{delegating_role}.json")
            if isinstance(md.signed, Root):
                for rolename, role in md.signed.roles.items():
                    for keyid in role.keyids:
                        self._load_key(rolename, md.signed.keys[keyid])
            elif isinstance(md.signed, Targets):
                if md.signed.delegations is None:
                    continue
                if md.signed.delegations.roles is not None:
                    for role in md.signed.delegations.roles.values():
                        for keyid in role.keyids:
                            self._load_key(
                                role.name, md.signed.delegations.keys[keyid]
                            )
                elif md.signed.delegations.succinct_roles is not None:
                    for bin in md.signed.delegations.succinct_roles.get_roles():
                        for keyid in  md.signed.delegations.keys.keys():
                            self._load_key(bin, md.signed.delegations.keys[keyid])


class InsecureFileKeyring(Keyring):
    """Private key management in plain text file

    loads secrets from plain text privkeys.json file for all delegating roles
    in this repository. This currently loads all delegating metadata to find
    the public keys.

    Supports writing secrets to disk with store_key().
    """

    def _load_key(self, rolename: str, key: Key):
        # Load a private key from env var or the private key file
        private = self._privkeyfile.get(key.keyid)
        if private:
            self[rolename].add(PrivateKey(key, private))

    def __init__(self) -> None:
        # defaultdict with an empy set as initial value
        try:
            with open("privkeys.json", "r") as f:
                self._privkeyfile: Dict[str, str] = json.loads(f.read())
        except json.JSONDecodeError as e:
            raise RuntimeError("Failed to read privkeys.json")
        except FileNotFoundError:
            self._privkeyfile = {}

        super().__init__()
        logger.info("Loaded keys for %d roles from privkeys.json", len(self))

    def generate_key(self) -> PrivateKey:
        "Generate a private key"
        keydict = generate_ed25519_key()
        del keydict["keyid_hash_algorithms"]
        private = keydict["keyval"].pop("private")
        return PrivateKey(Key.from_dict(keydict["keyid"], keydict), private)

    def store_key(self, role: str, key: PrivateKey) -> None:
        "Write private key to privkeys.json"

        # Add new key to keyring
        self[role].add(key)

        # write private key to privkeys file
        try:
            with open("privkeys.json", "r") as f:
                privkeyfile: Dict[str, str] = json.loads(f.read())
        except FileNotFoundError:
            privkeyfile = {}
        privkeyfile[key.public.keyid] = key.private
        with open("privkeys.json", "w") as f:
            f.write(json.dumps(privkeyfile, indent=2))

        logger.info(
            "Added key %s for role %s to keyring",
            key.public.keyid[:7],
            role,
        )

class EnvVarKeyring(Keyring):
    """Private key management using environment variables
    
    Load private keys from env variables (TUF_REPO_PRIVATE_KEY_*) for all
    delegating roles in this repository. This currently loads all delegating
    metadata to find the public keys.
    """

    def _load_key(self, rolename: str, key: Key):
        # Load a private key from env var or the private key file
        private = os.getenv(f"TUF_REPO_PRIVATE_KEY_{key.keyid}")
        if private:
            self[rolename].add(PrivateKey(key, private))

    def __init__(self) -> None:
        # defaultdict with an empy set as initial value
        super().__init__()
        logger.info("Loaded keys for %d roles from env vars", len(self))
