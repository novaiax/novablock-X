from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseV134Tests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual((ROOT / "RELEASE_VERSION").read_text().strip(), "v1.0.34")

    def test_recovery_fast_path_contract(self):
        src = (ROOT / "recovery_v134" / "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        self.assertIn("pollInterval", src)
        self.assertIn("5 * time.Millisecond", src)
        self.assertIn("closeBrowsersNative()", src)
        self.assertIn("go func() { setGate(true)", src)
        self.assertIn("go requestAppRestart()", src)
        self.assertNotIn("Set-DnsClientServerAddress", src)
        self.assertNotIn("ipconfig", src.lower())

    def test_updater_installs_recovery_layer_and_verifies_hash(self):
        src = (ROOT / "outils" / "update.bat").read_text(encoding="utf-8", errors="replace")
        self.assertIn("SHA256SUMS.txt", src)
        self.assertIn("update.exe", src)
        self.assertIn("--repair", src)
        self.assertIn("--status", src)

    def test_emergency_and_reactivation_are_v134_aware(self):
        emergency = (ROOT / "outils" / "EMERGENCY_RESET.ps1").read_text(encoding="utf-8", errors="replace")
        reactivate = (ROOT / "outils" / "REACTIVATE.ps1").read_text(encoding="utf-8", errors="replace")
        repair = (ROOT / "outils" / "REPARE_INTERNET.ps1").read_text(encoding="utf-8", errors="replace")
        self.assertIn("--maintenance-pause", emergency)
        self.assertIn("--repair", reactivate)
        self.assertIn("--status", reactivate)
        self.assertIn("--repair-network", repair)

    def test_workflow_builds_and_publishes_all_v134_assets(self):
        wf = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")
        for expected in ("actions/setup-go@v5", "go vet ./...", "update.exe", "rollback_1.33.exe", "SHA256SUMS.txt"):
            self.assertIn(expected, wf)


if __name__ == "__main__":
    unittest.main()
