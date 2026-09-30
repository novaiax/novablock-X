from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseV137Tests(unittest.TestCase):
    def test_release_version(self):
        self.assertEqual((ROOT / "RELEASE_VERSION").read_text().strip(), "v1.0.37")

    def test_recovery_fast_path_contract(self):
        src = (ROOT / "recovery_v134" / "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        self.assertIn("pollInterval", src)
        self.assertIn("5 * time.Millisecond", src)
        self.assertIn("closeBrowsersNative()", src)
        self.assertIn("go func() { setGate(true)", src)
        self.assertIn("go requestAppRestart()", src)
        self.assertRegex(src, r'"ucbrowser\.exe":\s*\{\}')
        self.assertRegex(src, r'"ucbrowserlauncher\.exe":\s*\{\}')
        self.assertNotIn("Set-DnsClientServerAddress", src)
        self.assertNotIn("ipconfig", src.lower())

    def test_emergency_maintenance_requires_recent_marker_and_has_no_downgrade(self):
        src = (ROOT / "recovery_v134" / "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        maintenance = src[src.index("func maintenancePause()") : src.index("func repairNetworkState()")]
        self.assertIn('markerRecent("shutdown.sentinel")', maintenance)
        self.assertIn('case "--maintenance-pause"', src)
        self.assertNotIn('case "--rollback"', src)
        self.assertNotIn("func rollback()", src)

    def test_recovery_requires_interactive_task_and_cleans_predecessors(self):
        src = (ROOT / "recovery_v134" / "cmd" / "recovery" / "main_windows.go").read_text(encoding="utf-8")
        install = src[src.index("func installOrRepair()") : src.index("func installSelfCopy()")]
        service = src[src.index("func serviceLoop()") : src.index("func runAsService()")]

        self.assertIn("validateInteractiveTask()", install)
        self.assertIn("<logontype>interactivetoken</logontype>", src)
        self.assertIn("app task must not run as LocalSystem", src)
        self.assertIn("validateInteractiveTaskXML(out, expected)", src)
        self.assertIn("registeredAppPath()", src)
        restart = src[src.index("func requestAppRestart()") : src.index("func terminateProcessesByName(")]
        self.assertIn("validateInteractiveTask()", restart)
        self.assertIn("serviceIsRunning() && freshHeartbeat", install)
        self.assertNotIn("cleanupPredecessorComponents(false)", install)
        self.assertLess(install.index('runBestEffort("sc.exe", "start", serviceName)'), install.index("waitFreshHeartbeat"))
        self.assertLess(install.index("waitFreshHeartbeat"), install.index("tightenServiceACL()"))
        self.assertLess(service.index("cleanupPredecessorComponents(true)"), service.index("nextHB :="))
        self.assertIn("waitForPredecessorRemoval", install)
        self.assertIn("installedBinaryMatchesSelf()", install)
        self.assertNotIn("os.Remove(dst)", src[src.index("func installSelfCopy()"):
                                              src.index("func fileSHA256(")])
        main_check = src[src.index("func mainRunning()") : src.index("func requestAppRestart()")]
        self.assertIn("mainMutexPresent()", main_check)
        self.assertIn("mainProcessMatchesInstallation()", main_check)
        self.assertIn('"main.pid"', main_check)
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
        self.assertIn('showMessage("NovaBlock v1.0.37 - echec"', src)
        self.assertIn('showMessage("NovaBlock v1.0.37", "Installation et controle de sante termines avec succes."', src)
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
        self.assertIn("--repair-firewall", src)

    def test_packaged_selftest_requires_popup_uia_dependencies(self):
        src = (ROOT / "novablock" / "release_selftest.py").read_text(encoding="utf-8")
        self.assertIn("from pywinauto import Desktop", src)
        self.assertIn('checks["uia_dependencies"]', src)
        self.assertIn("monitor.HAS_UIA", src)

    def test_reactivation_is_v137_aware(self):
        reactivate = (ROOT / "outils" / "REACTIVATE.ps1").read_text(encoding="utf-8", errors="replace")
        self.assertIn("v1.0.37", reactivate)
        self.assertIn("--repair", reactivate)
        self.assertIn("--status", reactivate)
        self.assertIn("Start-ScheduledTask -TaskName 'NovaBlockApp'", reactivate)
        self.assertIn("DNS familiaux IPv4 et IPv6 actifs", reactivate)
        self.assertIn("https://example.com", reactivate)
        self.assertNotIn("9.9.9.11", reactivate)

    def test_emergency_reset_preserves_all_gates(self):
        emergency = (ROOT / "outils" / "EMERGENCY_RESET.ps1").read_text(encoding="utf-8", errors="replace")
        self.assertIn("while ($chars.Count -lt 200)", emergency)
        self.assertIn("$saisie.MaxLength   = 200", emergency)
        self.assertIn("$saisie.ShortcutsEnabled = $false", emergency)
        self.assertIn("Test-FenetreBloquee", emergency)
        self.assertIn("$btn.Add_Click({\n    if (-not [string]::Equals", emergency.replace("\r\n", "\n"))
        self.assertIn("$script:logFile", emergency)
        self.assertIn("--maintenance-pause", emergency)

    def test_network_repairs_keep_the_filter_active(self):
        unstick = (ROOT / "outils" / "unstick_sockets.ps1").read_text(encoding="utf-8").lower()
        internet = (ROOT / "outils" / "REPARE_INTERNET.ps1").read_text(encoding="utf-8").lower()
        self.assertIn("--repair-firewall", unstick)
        self.assertIn("start-transcript", unstick)
        self.assertNotIn("stop-process -name novablock", unstick)
        self.assertNotIn("-resetserveraddresses", unstick)
        self.assertIn("--repair-firewall", internet)
        self.assertNotIn("$kw.deletevalue", internet)

    def test_workflow_builds_and_publishes_v137_assets(self):
        wf = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")
        for expected in ("actions/setup-go@v5", "go vet ./...", "update.exe", "SHA256SUMS.txt"):
            self.assertIn(expected, wf)
        self.assertIn("audit/local-protections", wf)
        self.assertIn("Application Continuity Runtime", wf)
        self.assertNotIn("NovaBlock recovery installer", wf)
        self.assertIn("github.com/tc-hib/go-winres@v0.3.3", wf)
        self.assertIn("--manifest cli --admin", wf)
        self.assertIn("publish_release:", wf)
        self.assertIn("github.event_name == 'workflow_dispatch'", wf)
        self.assertIn("inputs.publish_release == true", wf)
        self.assertNotIn("gh api -X DELETE", wf)

        package = wf[wf.index("- name: Package tools and checksums") : wf.index("- uses: actions/upload-artifact@v4")]
        self.assertIn("$safeTools = @(", package)
        self.assertNotIn("Copy-Item outils/*", package)
        listed = set(re.findall(r"^\s+'([^']+)'", package, flags=re.MULTILINE))
        self.assertEqual(listed, {
            "LISEZ-MOI.txt", "EMERGENCY_RESET.bat", "EMERGENCY_RESET.ps1",
            "REACTIVATE.bat", "REACTIVATE.ps1", "REPARE_INTERNET.ps1",
            "MESURE_BOOT.ps1", "unstick_sockets.bat", "unstick_sockets.ps1",
            "whitelist_site.bat", "whitelist_site.ps1",
            "update.bat",
        })
        self.assertNotIn("rollback_1.33.exe", wf)

    def test_docs_record_startup_fix_and_release_gate(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")

        self.assertIn("session Windows 0", readme)
        self.assertIn("**v1.0.37**", readme)
        self.assertIn("update.bat --local", readme)
        self.assertIn("78 règles", notes)
        self.assertIn("publication manuelle", notes)


if __name__ == "__main__":
    unittest.main()
