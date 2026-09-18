"""Interactive console for running the bot: live logs plus /start, /stop, /status.

Run it with `bot.bat` (Windows) or `./bot.sh`, or directly with
`python console.py`. The bot itself runs as a child process; this window only
supervises it, so stopping the console stops the bot too.

Why a supervisor and not just `python run.py`: conversion happens in a pool of
worker processes, and killing the parent alone can leave those orphaned. Stopping
from here takes the whole process tree down.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "bot.log"
IS_WINDOWS = os.name == "nt"

DIM = "\033[2m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
OFF = "\033[0m"


def enable_ansi() -> None:
    """Windows consoles need virtual terminal processing turned on explicitly."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if IS_WINDOWS:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def say(text: str = "") -> None:
    print(text, flush=True)


def stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


class Bot:
    """The bot as a supervised child process."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen[str] | None = None
        self.started_at: float | None = None
        self._expected_stop = False

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def uptime(self) -> str:
        if not self.running or self.started_at is None:
            return "-"
        return str(timedelta(seconds=int(time.time() - self.started_at)))

    def start(self) -> bool:
        if self.running:
            say(f"{YELLOW}Il bot è già in esecuzione (PID {self.proc.pid}).{OFF}")
            return False

        LOG_DIR.mkdir(exist_ok=True)
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")

        # A new process group lets us signal the bot and its workers together.
        extra = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if IS_WINDOWS
            else {"start_new_session": True}
        )

        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "run.py")],
                cwd=str(ROOT),
                env=env,
                # The bot must not inherit this console's stdin. If it does, its
                # output stalls the moment we block reading a command, and the
                # log pane silently stays empty while the bot runs fine.
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **extra,
            )
        except OSError as exc:
            say(f"{RED}Impossibile avviare il bot: {exc}{OFF}")
            return False

        self.started_at = time.time()
        self._expected_stop = False
        threading.Thread(target=self._pump, daemon=True).start()
        say(f"{GREEN}▶ Bot avviato (PID {self.proc.pid}).{OFF}")
        return True

    def _pump(self) -> None:
        """Forward the child's output to this console and to logs/bot.log."""
        proc = self.proc
        if proc is None or proc.stdout is None:
            return
        try:
            with LOG_FILE.open("a", encoding="utf-8") as handle:
                for line in proc.stdout:
                    line = line.rstrip()
                    # File first: the log on disk should not depend on the
                    # console print succeeding.
                    handle.write(f"{line}\n")
                    handle.flush()
                    say(line)
        except Exception as exc:
            # Swallowing this silently once cost an hour: the logs simply never
            # appeared and there was nothing to tell us why.
            say(f"{RED}Lettura dei log interrotta: {exc!r}{OFF}")

        code = proc.wait()
        if not self._expected_stop:
            colour = GREEN if code == 0 else RED
            say(f"{colour}■ Il bot si è chiuso da solo (codice {code}).{OFF}")
            say(f"{DIM}  Usa /start per riavviarlo.{OFF}")

    def _kill_tree(self) -> None:
        if self.proc is None:
            return
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                capture_output=True,
            )
        else:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def stop(self, timeout: float = 12.0, quiet: bool = False) -> bool:
        if not self.running:
            if not quiet:
                say(f"{YELLOW}Il bot non è in esecuzione.{OFF}")
            return False

        self._expected_stop = True
        if not quiet:
            say(f"{DIM}Arresto in corso…{OFF}")

        try:
            if IS_WINDOWS:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGINT)
        except Exception:
            pass

        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            if not quiet:
                say(f"{YELLOW}Non risponde, lo chiudo a forza.{OFF}")

        # Always sweep the tree: the conversion workers must not survive.
        self._kill_tree()
        if not quiet:
            say(f"{RED}■ Bot fermato.{OFF}")
        self.started_at = None
        return True

    def status(self) -> None:
        if self.running:
            say(f"  stato      {GREEN}in esecuzione{OFF}")
            say(f"  PID        {self.proc.pid}")
            say(f"  attivo da  {self.uptime}")
        else:
            say(f"  stato      {RED}fermo{OFF}")
        size = LOG_FILE.stat().st_size / 1024 if LOG_FILE.exists() else 0
        say(f"  log        {LOG_FILE}  ({size:.0f} kB)")


def show_logs(count: int = 30) -> None:
    if not LOG_FILE.exists():
        say(f"{DIM}Nessun log ancora.{OFF}")
        return
    lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    say(f"{DIM}── ultime {min(count, len(lines))} righe ──{OFF}")
    for line in lines[-count:]:
        say(line)
    say(f"{DIM}──{OFF}")


HELP = f"""
  {BOLD}/start{OFF}      avvia il bot
  {BOLD}/stop{OFF}       lo ferma (insieme ai worker di conversione)
  {BOLD}/restart{OFF}    lo riavvia
  {BOLD}/status{OFF}     stato, PID, da quanto è attivo
  {BOLD}/logs{OFF} [n]   ultime n righe dal file di log (default 30)
  {BOLD}/cls{OFF}        pulisce questa finestra
  {BOLD}/help{OFF}       questo elenco
  {BOLD}/quit{OFF}       ferma il bot ed esce
"""


def banner() -> None:
    say()
    say(f"{BOLD}{CYAN}  WhatsApp Sticker Converter — console{OFF}")
    say(f"{DIM}  I log compaiono qui sotto. Scrivi un comando e premi Invio.{OFF}")
    say(HELP)


def main() -> None:
    enable_ansi()
    banner()

    bot = Bot()
    say(f"{DIM}Il bot è fermo. Scrivi /start per avviarlo.{OFF}\n")

    try:
        while True:
            try:
                raw = input().strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not raw:
                continue

            parts = raw.lstrip("/").split()
            command, args = parts[0].lower(), parts[1:]

            if command in ("start", "avvia"):
                bot.start()
            elif command in ("stop", "ferma"):
                bot.stop()
            elif command in ("restart", "riavvia"):
                bot.stop(quiet=not bot.running)
                time.sleep(1)
                bot.start()
            elif command in ("status", "stato"):
                bot.status()
            elif command in ("logs", "log"):
                try:
                    count = int(args[0]) if args else 30
                except ValueError:
                    count = 30
                show_logs(count)
            elif command in ("cls", "clear"):
                os.system("cls" if IS_WINDOWS else "clear")
                banner()
            elif command in ("help", "aiuto", "?"):
                say(HELP)
            elif command in ("quit", "exit", "esci"):
                break
            else:
                say(f"{YELLOW}Comando sconosciuto: {raw}{OFF}  {DIM}(/help){OFF}")
    finally:
        if bot.running:
            say(f"\n{DIM}Chiusura: fermo il bot…{OFF}")
            bot.stop(quiet=True)
            say(f"{RED}■ Bot fermato.{OFF}")
        say(f"{DIM}Arrivederci.{OFF}")


if __name__ == "__main__":
    main()
