
# Repository Editor for TUF

## Overview

_Repository Editor for TUF_ project provides a command line tool to edit and
maintain a [TUF](https://theupdateframework.io/) repository. Project aims to:
 * Produce a command line tool for demos, tutorials, testing and and small
   scale repositories in general. In particular, support use cases of:
   * Repository maintainer _(repository setup, key rotations, delegations)_
   * Timestamp/snapshot automation _(hands-free, running on CI)_
   * Target file maintainer _(publishing targets)_
 * Smoke test the TUF Metadata API for repository functionality

## Status

_Repository Editor for TUF_ works already and can be used to create and maintain
TUF repositories for demo purposes.

It is also at early stages of development and should be considered
experimental and unstable:
 * Testing is minimal
 * Private key management is minimal: removing keys requires editing a file,
   using an existing key is not supported
 * No releases or packages are available

## How it works

### Metadata is stored in git

The tufrepo tool works in a git-stored TUF metadata directory: metadata files
are automatically added to git. Git is used for a few reasons:
 * This means the tool needs no state tracking as git knows whether a file
   has been modified already
 * Reviewing changes, committing them as logical chunks and reverting wrong
   changes becomes easy
 * publishing and sharing repositories (and even running tufrepo on CI)
   is possible

### Commands are used to edit metadata

'init' command initializes a new repository: the same results can be achieved
with individually editing each top level role, 'init' is just a short cut.

The 'edit' command modifies a single metadata file (there are many
sub-commands, see examples). The 'snapshot' command updates the repository
snapshot and timestamp. During 'edit' and 'snapshot' commands the tool takes
care of:
 * expiry updates
 * metadata version numbers
 * file name changes
 * signing (with all private keys available)

The 'sign' command signs metadata without otherwise modifying it.
Signing happens automatically during 'edit' and 'snapshot' but sometimes
all keys are not available at edit time -- in these cases signing without
modifying the signed content is useful.

The 'verify' command verifies repository validity.

### Key management

All of the metadata is stored in git and the git repository is meant to be
shareable publicly. This means private keys must be stored elsewhere.

tufrepo can currently read private key secrets from two places:
 * privkeys.json in the repo directory (this does not get committed to git).
   Encrypted keys are not yet supported.
 * environment variables. This is useful when running tufrepo on CI and reading
   the secrets from the CI secrets storage
The tool will automatically use the available keys to sign whenever signing is
needed.

tufrepo writes new keys (created during `edit <role> add-key`) to
privkeys.json.

This key management solution is preliminary and likely to change in the future.

## Testing in virtualenv

    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt -e .

    tufrepo --help

If you want to debug a specific command locally you can have a look at
`click` documentation about it: https://click.palletsprojects.com/en/8.1.x/testing/.
It may be  worth setting a temporary folder where you can test your command in
order to simulate tufrepo behavior.

## Examples

Note: The tool outputs very little currently: Running `git diff` once in a
while helps keep track of changes so far.

### Repository initialization

    # initialize a git repository for the metadata
    mkdir repo && cd repo
    git init .
    echo "privkeys.json" > .gitignore

    # Create top level metadata
    tufrepo init

    git commit -a -m "initial top-level metadata"

### Editing metadata

    # shorter expiry for timestamp
    tufrepo edit timestamp set-expiry 12 hours

    # require two of three root keys
    tufrepo edit root add-key root
    tufrepo edit root add-key root
    tufrepo edit root set-threshold root 2

    git commit -a -m "timestamp expiry & more root keys"

### Delegation

    # Add delegation (sign with targets key)
    tufrepo edit targets add-delegation --path "files/*" role1
    tufrepo edit targets add-key role1

    # Create the delegate targets role (sign with role1 key)
    tufrepo edit role1 init

    # Update snapshot/timestamp contents (sign with snapshot/timestamp keys)
    tufrepo snapshot

    git commit -a -m "Delegation to role1"

### Target info update example:

    # Developer adds target "files/file1.txt" (sign with role1 key)
    tufrepo edit role1 add-target files/file1.txt ../targets/files/file1.txt

    # Update snapshot/timestamp contents (sign with snapshot/timestamp key)
    tufrepo snapshot

    git commit -a -m "Add target 'files/file1.txt'"

## Contributing

Contributions are very welcome. If you wish to contribute code and have not
signed our contributor license agreement (CLA), our bot will update the issue
with details when you open a Pull Request. For any questions about the CLA
process, please refer to our [FAQ](https://cla.vmware.com/faq).

## License

The code is dual-licensed under MIT and Apache 2.0 licenses (for maximum
compatibility with TUF project), see [LICENSE-MIT](LICENSE-MIT) and
[LICENSE](LICENSE).
