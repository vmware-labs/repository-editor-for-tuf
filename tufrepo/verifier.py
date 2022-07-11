import logging
import os
import shutil

from tempfile import TemporaryDirectory
from typing import List, Optional, Tuple

from click.exceptions import ClickException
from securesystemslib.hash import digest_fileobject
from tuf.api.exceptions import ExpiredMetadataError, RepositoryError
from tuf.api.metadata import Snapshot, Targets
from tuf.ngclient.updater import Updater

from tufrepo.filesystem_fetcher import FilesystemFetcher

logger = logging.getLogger("tufrepo")


def add_if_validated(
    updater: Updater, delegators: List, role: str, delegator: str
):
    """Verify a given 'role' and if it has been successfully verified add it to
    the 'delegators'."""
    assert updater._trusted_set.snapshot is not None
    snapshot: Snapshot = updater._trusted_set.snapshot.signed

    try:
        metainfo = snapshot.meta[f"{role}.json"]
    except KeyError:
        raise ClickException(f"Snapshot is invalid: {role} not found in snapshot")

    filename = f"{metainfo.version}.{role}.json"
    try:
        with open(filename, "rb") as file:
            data = file.read()
    except FileNotFoundError:
        raise ClickException(f"Snapshot is invalid: file {filename} not found")

    logger.debug("Verifying %s", role)
    try:
        updater._trusted_set.update_delegated_targets(data, role, delegator)
        delegators.append((role, updater._trusted_set[role].signed))
    except ExpiredMetadataError as e:
        logger.warning("Delegated target %s has expired", role)
    except RepositoryError as e:
        raise ClickException(f"Delegated target {role} fails to validate") from e


### verify repository contents
def verify_repo(root_hash: Optional[str]):
    if not os.path.exists("1.root.json"):
        raise ClickException("Failed to find 1.root.json")

    if root_hash is not None:
        # verify initial root is what we expected
        with open("1.root.json") as initial_root:
            digest_object = digest_fileobject(initial_root)
        digest = digest_object.hexdigest()
        if digest != root_hash:
            raise ClickException(f"Unexpected hash digest {digest} for 1.root.json")

    # Do a normal client update to ensure metadata is good
    client_dir = TemporaryDirectory()
    shutil.copy("1.root.json", f"{client_dir.name}/root.json")
    fsfetcher = FilesystemFetcher({"http://localhost/fakeurl/": "."})
    try:
        updater = Updater(
            metadata_dir=client_dir.name,
            metadata_base_url="http://localhost/fakeurl/",
            target_base_url="http://localhost/fakeurl/",
            fetcher=fsfetcher,
        )
        updater.refresh()
    except RepositoryError as e:
        # TODO: improve this message by checking for common mistakes?
        raise ClickException("Top-level metadata fails to validate") from e

    # recursively verify all targets in delegation tree
    # This code is pretty horrible
    delegators: List[Tuple[str, Targets]] = [
        ("targets", updater._trusted_set["targets"].signed)
    ]
    while delegators:
        delegator_name, delegator = delegators.pop(0)
        if delegator.delegations is None:
            continue

        if delegator.delegations.roles is not None:
            for role in delegator.delegations.roles.values():
                add_if_validated(updater, delegators, role.name, delegator_name)

        if delegator.delegations.succinct_roles is not None:
            for bin_name in delegator.delegations.succinct_roles.get_roles():
                add_if_validated(updater, delegators, bin_name, delegator_name)

    deleg_count = len(updater._trusted_set) - 4

    print(f"Metadata with {deleg_count} delegated targets verified")
