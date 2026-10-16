import unittest
from types import SimpleNamespace
from unittest import mock

from claudio.cli import _resolve_secret_references


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class ResolveSecretReferencesTest(unittest.TestCase):
    def test_op_passthrough(self):
        with mock.patch("claudio.cli.subprocess.run", return_value=_proc(stdout="s3cret\n")) as run:
            out = _resolve_secret_references({"K": "op://vault/item/field"})
        self.assertEqual(out, {"K": "s3cret"})
        self.assertEqual(run.call_args.args[0], ["op", "read", "op://vault/item/field"])

    def test_plain_value_untouched(self):
        with mock.patch("claudio.cli.subprocess.run") as run:
            out = _resolve_secret_references({"K": "plain"})
        self.assertEqual(out, {"K": "plain"})
        run.assert_not_called()

    def test_keychain_success(self):
        with mock.patch("claudio.cli.sys.platform", "darwin"), mock.patch(
            "claudio.cli.subprocess.run", return_value=_proc(stdout="tok\n")
        ) as run:
            out = _resolve_secret_references({"K": "keychain://svc/acct"})
        self.assertEqual(out, {"K": "tok"})
        self.assertEqual(
            run.call_args.args[0],
            ["security", "find-generic-password", "-s", "svc", "-a", "acct", "-w"],
        )

    def test_malformed_refs_exit(self):
        for ref in ("keychain://", "keychain://svc", "keychain://svc/"):
            with self.subTest(ref=ref), mock.patch("claudio.cli.sys.platform", "darwin"), mock.patch(
                "claudio.cli.subprocess.run"
            ) as run:
                with self.assertRaises(SystemExit) as cm:
                    _resolve_secret_references({"K": ref})
                self.assertEqual(cm.exception.code, 1)
                run.assert_not_called()

    def test_non_darwin_exit(self):
        with mock.patch("claudio.cli.sys.platform", "linux"), mock.patch(
            "claudio.cli.subprocess.run"
        ) as run:
            with self.assertRaises(SystemExit) as cm:
                _resolve_secret_references({"K": "keychain://svc/acct"})
        self.assertEqual(cm.exception.code, 1)
        run.assert_not_called()

    def test_security_failure_exit(self):
        with mock.patch("claudio.cli.sys.platform", "darwin"), mock.patch(
            "claudio.cli.subprocess.run", return_value=_proc(returncode=44, stderr="not found\n")
        ):
            with self.assertRaises(SystemExit) as cm:
                _resolve_secret_references({"K": "keychain://svc/acct"})
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
