import base64
import os
import pathlib
import re
import subprocess
import tempfile
import unittest


class UpdateScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = pathlib.Path('outils/update.bat').read_text(encoding='utf-8', errors='ignore')
        cls.text = cls.source.lower()

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
        self.assertIn('nb_updater_local_app=%~f2', self.text)
        self.assertIn('nb_updater_local_recovery=%~f3', self.text)
        self.assertIn('get-filehash', self.text)
        self.assertIn('local_app', self.text)
        self.assertIn('local_recovery', self.text)

    def test_single_file_elevation_preserves_spaced_and_quoted_paths(self):
        self.assertNotIn('elevate_update.ps1', self.text)
        self.assertIn('-encodedcommand', self.text)
        self.assertIn('-verb runas', self.text)
        self.assertIn('pause', self.text)
        line = next(line for line in self.source.splitlines()
                    if line.startswith('powershell -NoProfile -ExecutionPolicy Bypass -Command'))
        command = re.search(r'-Command "(.*)"$', line).group(1)
        with tempfile.TemporaryDirectory() as temporary:
            capture = pathlib.Path(temporary) / 'encoded.txt'
            for local in (False, True):
                env = os.environ.copy()
                env.update({
                    'NB_UPDATER_SCRIPT': r"C:\Temp\Yann's folder\update.bat",
                    'NB_UPDATER_LOCAL_MODE': '1' if local else '0',
                    'NB_UPDATER_LOCAL_APP': r"C:\Temp\Yann's folder\NovaBlock.exe" if local else '',
                    'NB_UPDATER_LOCAL_RECOVERY': r"C:\Temp\Yann's folder\update.exe" if local else '',
                    'NB_CAPTURE_PATH': str(capture),
                })
                stub = ('function Start-Process { [CmdletBinding()] '
                        'param([string]$FilePath,[string[]]$ArgumentList,[string]$Verb) '
                        '[IO.File]::WriteAllText($env:NB_CAPTURE_PATH,$ArgumentList[-1]) }; ')
                result = subprocess.run(
                    ['powershell.exe', '-NoProfile', '-Command', stub + command],
                    env=env, capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                body = base64.b64decode(capture.read_text()).decode('utf-16le')
                self.assertIn(r"& 'C:\Temp\Yann''s folder\update.bat'", body)
                self.assertIn('exit $LASTEXITCODE', body)
                if local:
                    self.assertIn(r"'--local' 'C:\Temp\Yann''s folder\NovaBlock.exe'", body)
                    self.assertIn(r"'C:\Temp\Yann''s folder\update.exe'", body)
                else:
                    self.assertNotIn('--local', body)

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
        self.assertIn('get-netadapterbinding', self.text)
        self.assertIn('$v4 -notcontains $ip', self.text)
        self.assertIn('$v6 -notcontains $ip', self.text)

    def test_update_repairs_duplicate_firewall_rules_before_relaunch(self):
        self.assertIn('start "" /wait "%install_path%" --repair-firewall', self.text)
        self.assertIn('firewall-repair-report.json', self.text)
        self.assertIn('firewall_repair_error', self.text)
        self.assertIn('firewall_reboot', self.text)


if __name__ == '__main__':
    unittest.main()
