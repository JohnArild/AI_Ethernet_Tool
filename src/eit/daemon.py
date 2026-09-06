"""HTTP control daemon. Binds the management address; data ports have no IP."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from eit.config import Config, load_config
from eit.dataplane import DataPlane
from eit.models import FaultError, FaultSpec
from eit.profiles import list_profiles, merge_profile
from eit.runner import CommandError

log = logging.getLogger("eitd")


class Session:
    def __init__(self, plane: DataPlane, config: Config):
        self.plane = plane
        self.config = config
        self.lock = threading.Lock()
        self.spec: FaultSpec | None = None
        self.applied_at: float | None = None
        self.expires_at: float | None = None
        self._timer: threading.Timer | None = None
        self._flap_stop = threading.Event()
        self._flap_thread: threading.Thread | None = None

    def status(self) -> dict[str, Any]:
        with self.lock:
            spec = self.spec
            applied_at = self.applied_at
            expires_at = self.expires_at
        state = "pass-through"
        if spec and not spec.is_pass_through():
            state = "impaired"
        return {
            "state": state,
            "applied": spec.to_dict() if spec else None,
            "applied_at": applied_at,
            "expires_at": expires_at,
            "interfaces": self.plane.status(),
        }

    def apply(self, spec: FaultSpec) -> dict[str, Any]:
        spec.validate()
        duration = spec.duration_s
        if duration is None:
            duration = self.config.default_duration_s
            spec.duration_s = duration
        if duration > self.config.max_duration_s:
            raise FaultError(f"duration_s exceeds max {self.config.max_duration_s}")
        with self.lock:
            self._cancel_locked()
            self.plane.apply(spec)
            now = time.time()
            self.spec = spec
            self.applied_at = now
            self.expires_at = (now + duration) if duration else None
            if duration:
                self._timer = threading.Timer(duration, self._expire)
                self._timer.daemon = True
                self._timer.start()
            if spec.link_down and spec.flap_ms:
                self._flap_stop.clear()
                side = spec.link_down
                period = spec.flap_ms / 1000.0
                self._flap_thread = threading.Thread(
                    target=self._flap_loop,
                    args=(side, period),
                    daemon=True,
                    name="eit-flap",
                )
                self._flap_thread.start()
        log.info("applied fault: %s", spec.to_dict())
        return self.status()

    def clear(self) -> dict[str, Any]:
        with self.lock:
            self._cancel_locked()
            self.plane.clear()
            self.spec = FaultSpec(duration_s=None)
            self.applied_at = time.time()
            self.expires_at = None
        log.info("cleared faults; pass-through")
        return self.status()

    def prepare(self) -> dict[str, Any]:
        self.plane.prepare()
        return {"ok": True, "interfaces": self.plane.status()}

    def _expire(self) -> None:
        log.info("duration expired; clearing")
        try:
            self.clear()
        except Exception:
            log.exception("auto-clear failed")

    def _flap_loop(self, side: str, period: float) -> None:
        up = False
        while not self._flap_stop.wait(period):
            try:
                self.plane.set_link(side, up)
            except CommandError:
                log.exception("flap set_link failed")
            up = not up

    def _cancel_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._flap_stop.set()
        thread = self._flap_thread
        self._flap_thread = None
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=2.0)


def make_handler(session: Session, config: Config):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            log.info("%s " + fmt, self.address_string(), *args)

        def _send(self, code: int, body: dict[str, Any]) -> None:
            payload = json.dumps(body, indent=2).encode("utf-8") + b"\n"
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            if not raw:
                return {}
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise FaultError("JSON body must be an object")
            return data

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            try:
                if path in ("/v1/status", "/status"):
                    self._send(200, session.status())
                    return
                if path in ("/v1/profiles", "/profiles"):
                    self._send(200, {"profiles": list_profiles(config.profile_dir)})
                    return
                self._send(404, {"error": "not found"})
            except Exception as exc:
                log.exception("GET failed")
                self._send(500, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            try:
                data = self._read_json()
                if path in ("/v1/clear", "/clear"):
                    self._send(200, session.clear())
                    return
                if path in ("/v1/prepare", "/prepare"):
                    self._send(200, session.prepare())
                    return
                if path in ("/v1/faults", "/faults"):
                    spec = merge_profile(data, config.profile_dir)
                    self._send(200, session.apply(spec))
                    return
                self._send(404, {"error": "not found"})
            except (FaultError, json.JSONDecodeError, CommandError) as exc:
                self._send(400, {"error": str(exc)})
            except Exception as exc:
                log.exception("POST failed")
                self._send(500, {"error": str(exc)})

    return Handler


def serve(config: Config, session: Session) -> ThreadingHTTPServer:
    handler = make_handler(session, config)
    server = ThreadingHTTPServer((config.listen_host, config.listen_port), handler)
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EIT control daemon")
    parser.add_argument("--config", help="Path to config.json")
    parser.add_argument("--host", help="Override listen host")
    parser.add_argument("--port", type=int, help="Override listen port")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from pathlib import Path

    config = load_config(Path(args.config) if args.config else None)
    if args.host:
        config.listen_host = args.host
    if args.port:
        config.listen_port = args.port

    plane = DataPlane(config.lan, config.wan, assumed_link_bps=config.assumed_link_bps)
    session = Session(plane, config)
    server = serve(config, session)

    def shutdown(*_args: Any) -> None:
        log.info("shutting down")
        try:
            session.clear()
        except Exception:
            log.exception("clear on shutdown failed")
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    log.info(
        "listening on %s:%s lan=%s wan=%s",
        config.listen_host,
        config.listen_port,
        config.lan,
        config.wan,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
