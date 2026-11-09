"""Installed command-line entry point for My Trading Policy."""
import argparse
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys

TYPE_LABELS = {"stock": "股票（A股）", "index": "指数", "etf": "基金（ETF）",
               "lof": "基金（LOF）", "fund": "基金（场外）"}


def symbol_code(value):
    if not re.fullmatch(r"[0-9]{6}", value):
        raise argparse.ArgumentTypeError("代码必须是六位数字，例如 600519。")
    return value


def port_number(value):
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("端口必须是整数。") from None
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("端口必须在 1–65535 之间。")
    return port


def infer_type(symbol):
    """Convenience defaults only; overlapping code spaces require --type."""
    if symbol in {"000016", "000300", "000688", "000852", "000905", "000906"} or symbol.startswith("399"):
        return "index"
    if symbol.startswith(("15", "51", "56", "58")):
        return "etf"
    if symbol.startswith(("16", "50")):
        return "lof"
    if symbol.startswith(("00", "30", "60", "68", "43", "83", "87", "92")):
        return "stock"
    return "fund"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mtp", description="My Trading Policy · 行情看板")
    commands = parser.add_subparsers(dest="command", required=True)
    viewer = commands.add_parser("viewer", help="启动日 K 看板")
    viewer.add_argument("symbol", nargs="?", default="000300", type=symbol_code, help="六位代码，默认 000300")
    viewer.add_argument("--type", choices=TYPE_LABELS, help="标的类型；未指定时按代码规则推测，可在页面更改")
    viewer.add_argument("--port", type=port_number, default=8501, help="服务端口，默认 8501")
    viewer.add_argument("--no-browser", action="store_true", help="仅启动服务，不自动打开浏览器")
    args = parser.parse_args(argv)
    missing = [name for name in ("streamlit", "plotly") if importlib.util.find_spec(name) is None]
    if missing:
        parser.exit(1, "缺少看板依赖，请在当前环境安装：python -m pip install 'my-trading-policy[dashboard]'\n")
    kind = args.type or infer_type(args.symbol)
    env = os.environ.copy()
    env.update(MTP_VIEWER_SYMBOL=args.symbol, MTP_VIEWER_TYPE=kind)
    app = Path(__file__).resolve().parent / "dashboard" / "app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app),
               "--server.address=127.0.0.1", f"--server.port={args.port}",
               f"--server.headless={'true' if args.no_browser else 'false'}",
               "--browser.gatherUsageStats=false", "--theme.base=light",
               "--theme.primaryColor=#262626", "--theme.backgroundColor=#ffffff",
               "--theme.secondaryBackgroundColor=#f5f5f5", "--theme.textColor=#262626"]
    print(f"打开 {args.symbol} · {TYPE_LABELS[kind]}：http://127.0.0.1:{args.port}", flush=True)
    if args.type is None:
        print("类型按代码规则推测；同码标的请使用 --type 或在页面更改。", flush=True)
    print("按 Ctrl+C 停止看板。端口被占用时可使用 --port 8502。", flush=True)
    try:
        return subprocess.call(command, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
