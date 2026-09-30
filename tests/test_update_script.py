import pathlib
import unittest


class UpdateScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pathlib.Path('outils/update.bat').read_text(encoding='utf-8', errors='ignore').lower()
        cls.elevation = pathlib.Path('outils/elevate_update.ps1').read_text(encoding='utf-8', errors='ignore').lower()

    def test_waits_for_process_exit_before_swap(self):
        self.assertIn('wait_process_exit', self.text)
        self.assertIn('tasklist', self.text)
        self.assertIn('novablock.exe', self.text)

    def test_does_not_swap_when_process_is_still_alive(self):
        self.assertIn('process_still_running', self.text)
        self.assertIn('goto :cleanup_fail', self.text)

    def test_retry_loop_exists_for_file_move(self):
        self.assertIn('retry_move', self.text)
        self.assertIn('move /y', self.text)

    def test_maintenance_never_forces_process_or_hosts_access(self):
        for forbidden in ('taskkill', 'stop-process', 'schtasks /end', 'takeown', 'icacls'):
            self.assertNotIn(forbidden, self.text)

    def test_local_verified_install_mode_exists(self):
        self.assertIn('if /i "%~1"=="--local"', self.text)
        self.assertIn('elevate_update.ps1', self.text)
        self.assertIn('-localapp "%~f2" -localrecovery "%~f3"', self.text)
        self.assertIn('get-filehash', self.text)
        self.assertIn('local_app', self.text)
        self.assertIn('local_recovery', self.text)

    def test_elevation_relay_preserves_spaced_paths(self):
        self.assertIn('-encodedcommand', self.elevation)
        self.assertIn("replace(\"'\", \"''\")", self.elevation)
        self.assertIn("'--local'", self.elevation)
        self.assertIn('$lastExitCode'.lower(), self.elevation)

    def test_local_checksum_commands_do_not_leak_cmd_caret_into_powershell(self):
        self.assertIn('[io.file]::writealllines', self.text)
        self.assertIn('[string[]]$lines=', self.text)
        self.assertIn('foreach($line in (get-content', self.text)
        self.assertNotIn("@($a+'  novablock.exe',$r+'  update.exe') ^|", self.text)
        self.assertNotIn("get-content '%sums_tmp%' ^|", self.text)

    def test_core_swap_has_recoverable_previous_copy(self):
        self.assertIn('previous_file', self.text)
        self.assertIn('core_swapped', self.text)
        self.assertIn('coeur precedent restaure', self.text)
        self.assertIn('complete health=0', self.text)
        self.assertIn('failed core_swapped=', self.text)

    def test_health_checks_filter_and_benign_https(self):
        self.assertIn('dns familiaux ipv4 et ipv6 actifs', self.text)
        self.assertIn(':wait_family_dns', self.text)
        self.assertIn('dns_waited', self.text)
        self.assertIn('[void][system.net.dns]::gethostaddresses', self.text)
        self.assertNotIn("gethostaddresses('www.google.com')^|out-null", self.text)
        self.assertIn('https://example.com', self.text)


if __name__ == '__main__':
    unittest.main()
