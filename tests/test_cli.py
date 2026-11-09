import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trading_analysis.cli import main


class CLITests(unittest.TestCase):
    def test_launch_from_another_directory(self):
        previous = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                with patch('trading_analysis.cli.subprocess.call', return_value=0) as call:
                    self.assertEqual(main(['viewer', '000001', '--type', 'index', '--port', '8502', '--no-browser']), 0)
                command = call.call_args.args[0]
                self.assertTrue(Path(command[4]).is_file())
                self.assertIn('--server.port=8502', command)
                self.assertIn('--server.headless=true', command)
                env = call.call_args.kwargs['env']
                self.assertEqual(env['MTP_VIEWER_SYMBOL'], '000001')
                self.assertEqual(env['MTP_VIEWER_TYPE'], 'index')
        finally:
            os.chdir(previous)

    def test_default_and_inferred_types(self):
        for arguments, symbol, kind in [([], '000300', 'index'), (['600519'], '600519', 'stock'),
                                        (['510300'], '510300', 'etf'), (['050025'], '050025', 'fund')]:
            with patch('trading_analysis.cli.subprocess.call', return_value=0) as call:
                main(['viewer', *arguments])
            self.assertEqual(call.call_args.kwargs['env']['MTP_VIEWER_SYMBOL'], symbol)
            self.assertEqual(call.call_args.kwargs['env']['MTP_VIEWER_TYPE'], kind)
            self.assertIn('--server.headless=false', call.call_args.args[0])

    def test_invalid_input_never_starts_server(self):
        for args in [['viewer', 'abc'], ['viewer', '--port', '0'], ['viewer', '--type', 'bad']]:
            with patch('trading_analysis.cli.subprocess.call') as call:
                with self.assertRaises(SystemExit) as error:
                    main(args)
                self.assertEqual(error.exception.code, 2)
                call.assert_not_called()

    def test_cli_defaults_reach_page(self):
        import pandas as pd
        from streamlit.testing.v1 import AppTest
        from trading_analysis.dashboard.data import add_averages
        from trading_analysis.data.akshare_provider import DataBundle
        frame = add_averages(pd.DataFrame(dict(date=pd.date_range('2026-01-01', periods=2),
                                             open=[1., 2.], high=[2., 3.], low=[1., 2.], close=[2., 3.])))
        bundle = DataBundle(frame, {'nav': False, 'api': 'test'})
        app_path = Path(__file__).resolve().parents[1] / 'src/trading_analysis/dashboard/app.py'
        with patch.dict(os.environ, MTP_VIEWER_SYMBOL='600519', MTP_VIEWER_TYPE='stock'):
            with patch('trading_analysis.dashboard.data.load_history', return_value=bundle):
                app = AppTest.from_file(str(app_path)).run()
                self.assertFalse(app.exception)
                self.assertEqual(app.text_input[0].value, '600519')
                self.assertEqual(app.selectbox[0].value, '股票（A股）')
                self.assertEqual(app.subheader[0].value, '600519 · 股票（A股）')


if __name__ == '__main__':
    unittest.main()
