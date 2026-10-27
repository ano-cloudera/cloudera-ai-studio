#!/usr/bin/env python3
import json
import subprocess
import time
import urllib.request

import websockets.sync.client as ws

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9229


def main() -> None:
    proc = subprocess.Popen(
        [
            CHROME,
            f"--remote-debugging-port={PORT}",
            "--user-data-dir=/tmp/m9-console-cap",
            "--remote-allow-origins=*",
            "--headless=new",
            "--window-size=1440,900",
            "http://127.0.0.1:3001/",
        ],
        stderr=subprocess.PIPE,
    )
    try:
        time.sleep(3)
        page = next(
            t for t in json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list").read())
            if t.get("type") == "page"
        )
        socket = ws.connect(page["webSocketDebuggerUrl"], max_size=8_000_000)
        mid = 0

        def send(method: str, params: dict | None = None) -> None:
            nonlocal mid
            mid += 1
            socket.send(json.dumps({"id": mid, "method": method, "params": params or {}}))

        send("Runtime.enable")
        send("Log.enable")
        deadline = time.time() + 130
        while time.time() < deadline:
            raw = socket.recv()
            msg = json.loads(raw)
            if msg.get("method") == "Runtime.exceptionThrown":
                print("EXCEPTION:", json.dumps(msg.get("params"), indent=2)[:4000])
            if msg.get("method") == "Log.entryAdded":
                entry = msg["params"]["entry"]
                if entry.get("level") in {"error", "warning"}:
                    print(f"LOG {entry.get('level')}: {entry.get('text')}")
    finally:
        proc.terminate()
        err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        if err.strip():
            print("CHROME STDERR:", err[-2000:])


if __name__ == "__main__":
    main()
