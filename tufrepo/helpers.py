# Copyright 2021 VMware, Inc.
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Some helpers for editing Metadata"""

from click.exceptions import ClickException
from datetime import datetime

from tuf.api.metadata import Key, Metadata, Root, Signed, Targets


def set_threshold(self: Signed, delegate: str, threshold: int):
    role = None
    if isinstance(self, Root):
        role = self.roles.get(delegate)
    elif isinstance(self, Targets):
        if self.delegations is not None:
            role = self.delegations.roles.get(delegate)
    else:
        raise ClickException(f"Not a delegator")

    if role is None:
        raise ClickException(f"Role {delegate} not found")
    role.threshold = threshold


def add_key(self: Signed, delegator: str, delegate: str, key: Key):
    if isinstance(self, Root) or isinstance(self, Targets):
        try:
            self.add_key(key, delegate)
        except ValueError:
            raise ClickException(f"{delegator} does not delegate to {delegate}")
    else:
        raise ClickException(f"{delegator} is not delegating metadata")


def remove_key(self: Signed, delegator: str, delegate: str, keyid: str):
    if isinstance(self, Root) or isinstance(self, Targets):
        try:
            self.revoke_key(keyid, delegate)
        except ValueError:
            raise ClickException(f"{delegator} does not delegate to {delegate}")
    else:
        raise ClickException(f"{delegator} is not delegating metadata")
