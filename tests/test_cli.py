import os
import subprocess
import tempfile
from typing import Any, Callable, Dict, List, NamedTuple, Optional
import unittest

# Test runner decorator: Runs the test as a set of SubTests,
def run_sub_tests_with_dataset(dataset: Dict[str, Any]):
    def real_decorator(function: Callable[[unittest.TestCase, Any], None]):
        def wrapper(test_cls: unittest.TestCase):
            for case, data in dataset.items():
                with test_cls.subTest(case=case):
                    function(test_cls, data)
        return wrapper
    return real_decorator


class TestCLI(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.cwd = self.tempdir.name

    def tearDown(self):
        self.tempdir.cleanup()

    def assertStartsWith(self, haystack:str,  needle: str):
        if not haystack.startswith(needle):
            raise AssertionError(
                f"Expected '{needle}...', got '{haystack[:len(needle)]}...'"
            )

    def _run(self, args: str, expected_out:Optional[str]="", expected_err:Optional[str]="") -> subprocess.CompletedProcess:
        proc = subprocess.run(
            args=["tufrepo"] + args.split(),
            capture_output=True, 
            cwd=self.cwd,
            text=True
        )
        if expected_out is not None:
           self.assertEqual(proc.stdout, expected_out)
        if expected_err is not None:
            if proc.stderr != expected_err:
                print(proc.stderr)
            self.assertEqual(proc.stderr, expected_err)
        self.assertEqual(proc.returncode, 0)

        return proc
 
    Data = NamedTuple("Data", [("argv", str), ("expect_out", str)])
    valid_commands: Dict[str, Data] = {
        "no args": Data("", "Usage: tufrepo [OPTIONS] COMMAND [ARGS]"),
        "help": Data("--help", "Usage: tufrepo [OPTIONS] COMMAND [ARGS]"),
        "verify": Data("verify --help", "Usage: tufrepo verify "),
        "sign": Data("sign --help", "Usage: tufrepo sign "),
        "snapshot": Data ("snapshot --help", "Usage: tufrepo snapshot "),
        "edit 1": Data("edit", "Usage: tufrepo edit "),
        "edit 2": Data("edit --help", "Usage: tufrepo edit "),
        "add-delegation": Data("edit x add-delegation --help", "Usage: tufrepo edit ROLE add-delegation "),
        "add-key": Data("edit x add-key --help", "Usage: tufrepo edit ROLE add-key "),
        "add-target": Data("edit x add-target --help", "Usage: tufrepo edit ROLE add-target "),
        "init": Data("edit x init --help", "Usage: tufrepo edit ROLE init "),
        "remove-delegation": Data("edit x remove-delegation --help", "Usage: tufrepo edit ROLE remove-delegation "),
        "remove-key": Data("edit x remove-key --help", "Usage: tufrepo edit ROLE remove-key "),
        "set-expiry": Data("edit x set-expiry --help", "Usage: tufrepo edit ROLE set-expiry "),
        "set-threshold": Data("edit x set-threshold --help", "Usage: tufrepo edit ROLE set-threshold "),
        "touch": Data("edit x touch --help", "Usage: tufrepo edit ROLE touch "),
    }
    @run_sub_tests_with_dataset(valid_commands)
    def test_basics(self, data: Data):
        """Test (mostly help) commands that work without metadata"""
        proc = self._run(data.argv, expected_out=None)
        self.assertStartsWith(proc.stdout, data.expect_out)

    def test_repo_manual_init(self):
        """Test (roughly) the tutorial from README"""
        subprocess.run(["git", "init", "."], cwd=self.cwd, capture_output=True)
        subprocess.run(["git", "config", "--local", "user.name", "test"], cwd=self.cwd)
        subprocess.run(["git", "config", "--local", "user.email", "test@example.com"], cwd=self.cwd)

        # Create initial metadata
        self._run("edit root init")
        self._run("edit root add-key root")
        self._run("edit root add-key snapshot")
        self._run("edit root add-key timestamp")
        self._run("edit root add-key targets")
        self._run("edit timestamp init")
        self._run("edit snapshot init")
        self._run("edit targets init")
        self._run("snapshot")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "Initial metadata"], cwd=self.cwd, capture_output=True)

        self.assertIn("Metadata with 0 delegated targets verified", proc.stdout)
        self.assertIn("Keyring contains keys for [root, snapshot, targets, timestamp]", proc.stdout)
        files = {".git", "1.root.json", "1.snapshot.json", "1.targets.json", "privkeys.json", "timestamp.json"}
        self.assertEqual(set(os.listdir(self.cwd)), files)

    def test_repo_management(self):
        """Test (roughly) the tutorial from README"""
        subprocess.run(["git", "init", "."], cwd=self.cwd, capture_output=True)
        subprocess.run(["git", "config", "--local", "user.name", "test"], cwd=self.cwd)
        subprocess.run(["git", "config", "--local", "user.email", "test@example.com"], cwd=self.cwd)

        # Create initial metadata
        self._run("init")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "Initial metadata"], cwd=self.cwd, capture_output=True)

        self.assertIn("Metadata with 0 delegated targets verified", proc.stdout)
        self.assertIn("Keyring contains keys for [root, snapshot, targets, timestamp]", proc.stdout)
        files = {".git", "1.root.json", "1.snapshot.json", "1.targets.json", "privkeys.json", "timestamp.json"}
        self.assertEqual(set(os.listdir(self.cwd)), files)

        self._run("edit root add-key root")
        self._run("edit root set-threshold root 2")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "root edit"], cwd=self.cwd, capture_output=True)

        self.assertStartsWith(proc.stdout, "Metadata with 0 delegated targets verified")
        files.add("2.root.json")
        self.assertEqual(set(os.listdir(self.cwd)), files)

        # Add new role, delegate to role
        self._run("edit targets add-delegation --path 'files/*' role1")
        self._run("edit targets add-key role1")
        self._run("edit role1 init")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "Add role, delegate"], cwd=self.cwd, capture_output=True)

        self.assertStartsWith(proc.stdout, "Metadata with 0 delegated targets verified")
        files |= { "2.targets.json", "1.role1.json" }
        self.assertEqual(set(os.listdir(self.cwd)), files)

        # Update snapshot
        self._run("snapshot")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "snapshot"], cwd=self.cwd, capture_output=True)

        self.assertStartsWith(proc.stdout, "Metadata with 1 delegated targets verified")
        files -= { "1.snapshot.json", "1.targets.json" }
        files.add("2.snapshot.json")
        self.assertEqual(set(os.listdir(self.cwd)), files)

        # Add target to role1 (don't add file to git)
        self._run("edit role1 add-target --no-target-in-repo files/timestamp.json timestamp.json")

        # Add target to role1 (also add target and hash-prefixed symlinks to git)
        with open(f"{self.cwd}/new-target", "w") as f:
            f.write("hello")
        self._run("edit role1 add-target files/new-target ./new-target")

        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "Add target"], cwd=self.cwd, capture_output=True)

        self.assertStartsWith(proc.stdout, "Metadata with 1 delegated targets verified")
        files |= { "2.role1.json", "new-target", "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824.new-target" }
        self.assertEqual(set(os.listdir(self.cwd)), files)

        # update snapshot
        self._run("snapshot")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "Add target"], cwd=self.cwd, capture_output=True)

        self.assertStartsWith(proc.stdout, "Metadata with 1 delegated targets verified")
        files -= { "1.role1.json", "2.snapshot.json" }
        files.add("3.snapshot.json")
        self.assertEqual(set(os.listdir(self.cwd)), files)

        # Make a timestamp update
        self._run("edit timestamp touch")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "commit", "-a", "-m", "Add target"], cwd=self.cwd, capture_output=True)

        self.assertStartsWith(proc.stdout, "Metadata with 1 delegated targets verified")
        self.assertEqual(set(os.listdir(self.cwd)), files)

        # Remove a target, update snapshot
        proc = self._run("edit role1 remove-target files/new-target", expected_out=None)
        self.assertStartsWith(proc.stdout, "Removed files/new-target")
        self._run("snapshot")
        subprocess.run(["git", "commit", "-a", "-m", "Remove target"], cwd=self.cwd, capture_output=True)

        files -= { "3.snapshot.json", "2.role1.json" }
        files |= { "4.snapshot.json", "3.role1.json" }
        self.assertEqual(set(os.listdir(self.cwd)), files)

        # Remove delegation, remove delegated role
        self._run("edit targets remove-delegation role1")
        self._run("snapshot")
        proc = self._run("verify", expected_out=None)
        subprocess.run(["git", "rm", "3.role1.json"], cwd=self.cwd, capture_output=True)
        subprocess.run(["git", "commit", "-a", "-m", "Remove delegation"], cwd=self.cwd, capture_output=True)

        self.assertStartsWith(proc.stdout, "Metadata with 0 delegated targets verified")
        files -= { "4.snapshot.json", "2.targets.json", "3.role1.json" }
        files |= { "5.snapshot.json", "3.targets.json" }
        self.assertEqual(set(os.listdir(self.cwd)), files)

if __name__ == '__main__':
    unittest.main()
