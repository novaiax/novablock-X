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

    def test_recovery_requires_interactive_task_and_cleans_predecessors(self):
        src = (ROOT / "recovery_v134" / "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        install = src[src.index("func installOrRepair()") : src.index("func installSelfCopy()")]
        service = src[src.index("func serviceLoop()") : src.index("func runAsService()")]

        self.assertIn("validateInteractiveTask()", install)
        self.assertIn("<logontype>interactivetoken</logontype>", src)
        self.assertIn("app task must not run as LocalSystem", src)
        self.assertIn('strings.Contains(compact, "--service-run")', src)
        self.assertIn("serviceIsRunning() && freshHeartbeat", install)
        self.assertNotIn("cleanupPredecessorComponents(false)", install)
        self.assertLess(install.index('runBestEffort("sc.exe", "start", serviceName)'), install.index("waitFreshHeartbeat"))
        self.assertLess(install.index("waitFreshHeartbeat"), install.index("tightenServiceACL()"))
        self.assertLess(service.index("cleanupPredecessorComponents(true)"), service.index("nextHB :="))
        self.assertIn("waitForPredecessorRemoval", install)
        self.assertIn("installedBinaryMatchesSelf()", install)
        self.assertIn("!predecessorServicesPresent()", install)
        self.assertIn("forceStuckProcess = forceStuckProcess && isLocalSystem()", src)
        self.assertIn("terminateProcessesByName(predecessorProcessNames)", src)
        cleanup = src[src.index("func cleanupPredecessorComponents(") : src.index("func predecessorServicesPresent()")]
        self.assertLess(
            cleanup.index('runLoggedBestEffort("sc.exe", "delete", name)'),
            cleanup.index("terminateProcessesByName(predecessorProcessNames)"),
        )
        predecessor_names = src[src.index("var predecessorProcessNames") : src.index("func main()")]
        self.assertNotIn('"novablock.exe"', predecessor_names)

    def test_double_click_reports_success_or_failure(self):
        src = (ROOT / "recovery_v134" / "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        self.assertIn("interactiveLaunch := len(os.Args) == 1", src)
        self.assertIn('showMessage("NovaBlock v1.0.34 - echec"', src)
        self.assertIn('showMessage("NovaBlock v1.0.34", "Installation et controle de sante termines avec succes."', src)
        self.assertIn('user32.NewProc("MessageBoxW")', src)

    def test_partial_install_acl_is_repaired_only_as_local_system(self):
        src = (ROOT / "recovery_v134" / "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        install = src[src.index("func installOrRepair()") : src.index("func installSelfCopy()")]
        repair = src[src.index("func repairServiceACLAsSystem()") : src.index("func ensureServiceMaintenanceAccess()")]
        maintenance = src[src.index("func ensureServiceMaintenanceAccess()") : src.index("func waitForServiceStop(")]

        self.assertIn('case "--service-acl-repair":', src)
        self.assertIn("if !isLocalSystem()", repair)
        self.assertIn("service ACL repair is restricted to LocalSystem", repair)
        self.assertIn("S-1-5-18", src)
        self.assertLess(
            install.index("ensureServiceMaintenanceAccess()"),
            install.index('runBestEffort("sc.exe", "stop", serviceName)'),
        )
        self.assertIn("CCDCLCSWRPWPDTLOCRSDRCWDWO", src)
        self.assertIn('"/RU", "SYSTEM"', maintenance)
        self.assertIn('runBestEffort("schtasks.exe", "/Delete", "/TN", aclRepairTask, "/F")', maintenance)
        self.assertIn("if err = loosenServiceACL(); err == nil", maintenance)

    def test_updater_installs_recovery_layer_and_verifies_hash(self):
        src = (ROOT / "outils" / "update.bat").read_text(encoding="utf-8", errors="replace")
        self.assertIn("SHA256SUMS.txt", src)
        self.assertIn("update.exe", src)
        self.assertIn("--repair", src)
        self.assertIn("--status", src)

    def test_packaged_selftest_requires_popup_uia_dependencies(self):
        src = (ROOT / "novablock" / "release_selftest.py").read_text(encoding="utf-8")
        self.assertIn("from pywinauto import Desktop", src)
        self.assertIn('checks["uia_dependencies"]', src)
        self.assertIn("monitor.HAS_UIA", src)

    def test_emergency_and_reactivation_are_v134_aware(self):
        emergency = (ROOT / "outils" / "EMERGENCY_RESET.ps1").read_text(encoding="utf-8", errors="replace")
        reactivate = (ROOT / "outils" / "REACTIVATE.ps1").read_text(encoding="utf-8", errors="replace")
        repair = (ROOT / "outils" / "REPARE_INTERNET.ps1").read_text(encoding="utf-8", errors="replace")
        self.assertIn("--maintenance-pause", emergency)
        self.assertIn("--repair", reactivate)
        self.assertIn("--status", reactivate)
        self.assertIn("Start-ScheduledTask -TaskName 'NovaBlockApp'", reactivate)
        self.assertIn("DNS familiaux IPv4 et IPv6 actifs", reactivate)
        self.assertIn("https://example.com", reactivate)
        self.assertNotIn("9.9.9.11", reactivate)
        self.assertIn("--repair-network", repair)

    def test_workflow_builds_and_publishes_all_v134_assets(self):
        wf = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")
        for expected in ("actions/setup-go@v5", "go vet ./...", "update.exe", "rollback_1.33.exe", "SHA256SUMS.txt"):
            self.assertIn(expected, wf)
        self.assertIn("fix/startup-ui-recovery", wf)
        self.assertIn("github.com/tc-hib/go-winres@v0.3.3", wf)
        self.assertIn("--manifest cli --admin", wf)
        self.assertIn("publish_release:", wf)
        self.assertIn("github.event_name == 'workflow_dispatch'", wf)
        self.assertIn("inputs.publish_release == true", wf)

    def test_docs_record_startup_fix_and_release_gate(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")

        self.assertIn("session Windows 0", readme)
        self.assertIn("candidate de réparation, non publiée", readme)
        self.assertIn("update.bat --local", readme)
        self.assertIn("validation d'un redémarrage Windows complet", notes)
        self.assertIn("publication n'est plus automatique", notes)


if __name__ == "__main__":
    unittest.main()
