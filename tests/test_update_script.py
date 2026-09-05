import pathlib
import unittest


class UpdateScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pathlib.Path('outils/update.bat').read_text(encoding='utf-8', errors='ignore').lower()

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


if __name__ == '__main__':
    unittest.main()
