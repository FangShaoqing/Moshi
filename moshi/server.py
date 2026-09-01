"""V4+ 服务层（server）—— 她作为"电话总机"：任何消息来了，她作答；状态持久化。

通道插头（可并行接入，都是同一个 Session/同一个她）：
- `POST /v1/chat/completions`  —— OpenAI 兼容（QClaw / OpenClaw 自定义 API 直接填这个地址）
- `POST /onebot/`              —— OneBot v11 HTTP 回调（NapCat/QQ 小号；快速回复 {"reply": ...}）
- `GET  /healthz`              —— 健康检查
- `POST /tick`                 —— 定时主动（"她会突然想起你"；需 onebot_api + qq_user_id 配置）

运行：
  python -m moshi.server [--seed N] [--port P] [--bind HOST] [--mode verify]
配置（可选覆盖）：config/service.json —— {"seed", "port", "bind", "onebot_api", "qq_user_id", "mode"}
只依赖标准库（transport 用 http.server；DeepSeek 仍走 urllib）。
"""

from __future__ import annotations

import argparse
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .runtime import Session

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "service.json"


def _load_config() -> dict:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _post_json(url: str, payload: dict, timeout: int = 10) -> dict | None:
    try:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[server] post 失败 {url}: {e}")
        return None


def _onebot_text(event: dict) -> str:
    """OneBot v11 事件 → 纯文本（兼容 str 消息与富文本段列表）。"""
    raw = event.get("raw_message")
    if raw:
        return str(raw)
    msg = event.get("message", "")
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        return "".join(str(s.get("data", {}).get("text", "")) for s in msg if s.get("type") == "text")
    return ""


def make_handler(session: Session, cfg: dict) -> type[BaseHTTPRequestHandler]:
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _log(self, msg: str) -> None:
            print(f"[server] {msg}")

        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}

        def do_GET(self) -> None:                      # 健康检查
            if self.path.rstrip("/") in ("/healthz", "/health", ""):
                self._send(200, {"ok": True, "seed": session.seed,
                                 "age": session.she.age, "warning": session.warning})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            path = self.path.rstrip("/")
            if path == "/v1/chat/completions":
                self._chat_completions()
            elif path == "/onebot":
                self._onebot()
            elif path == "/tick":
                self._tick()
            else:
                self._send(404, {"error": "not found"})

        # ── OpenAI 兼容（QClaw / OpenClaw 自定义 API）──
        def _chat_completions(self) -> None:
            body = self._read_json()
            messages = body.get("messages", []) or []
            last_user = next((m for m in reversed(messages)
                              if m.get("role") == "user"), None)
            text = (last_user or {}).get("content", "")
            if isinstance(text, list):        # 兼容 content 为段列表
                text = "".join(str(s.get("text", "")) for s in text if isinstance(s, dict))
            with lock:
                out = session.on_message(str(text))
            self._send(200, {
                "id": "moshi", "object": "chat.completion", "created": 0,
                "model": "moshi-chenmoshi",
                "choices": [{"index": 0, "message": {"role": "assistant",
                                                     "content": out["reply"]},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })

        # ── OneBot v11 HTTP 回调（NapCat/QQ）──
        def _onebot(self) -> None:
            event = self._read_json()
            if event.get("post_type") != "message":
                self._send(200, {"ok": True})
                return
            text = _onebot_text(event)
            with lock:
                out = session.on_message(text)
            self._log(f"onebot {event.get('message_type')}@{event.get('user_id')}: {out['reply'][:60]}")
            # 优先：经 onebot_api 主动推送（可靠）；未配置：快速回复 {"reply": ...}
            api = cfg.get("onebot_api", "")
            uid = cfg.get("qq_user_id", "")
            if api and uid:
                _post_json(api.rstrip("/") + "/send_private_msg",
                           {"user_id": int(uid), "message": out["reply"]})
                self._send(200, {"ok": True})
            else:
                self._send(200, {"reply": out["reply"]})

        # ── 定时主动（她会突然想起你）──
        def _tick(self) -> None:
            with lock:
                text = session.tick()
            if not text:
                self._send(200, {"sent": False})
                return
            api = cfg.get("onebot_api", "")
            uid = cfg.get("qq_user_id", "")
            if api and uid:
                ok = _post_json(api.rstrip("/") + "/send_private_msg",
                                {"user_id": int(uid), "message": text})
                self._send(200, {"sent": bool(ok), "text": text})
            else:
                self._send(200, {"sent": False, "text": text,
                                 "note": "未配置 onebot_api/qq_user_id（仅返回文本）"})

        def log_message(self, fmt: str, *args) -> None:   # 安静一点
            pass

    return Handler


def main() -> None:
    cfg = _load_config()
    ap = argparse.ArgumentParser(description="Moshi 服务层（通道无关）")
    ap.add_argument("--seed", type=int, default=cfg.get("seed", 20260827))
    ap.add_argument("--port", type=int, default=cfg.get("port", 8901))
    ap.add_argument("--bind", default=cfg.get("bind", "127.0.0.1"))
    ap.add_argument("--mode", default=cfg.get("mode", "verify"),
                    choices=("verify", "production"),
                    help="运行标签（verify=验证期 / production=正式期）")
    ap.add_argument("--mode-policy", default=cfg.get("mode_policy", "warn"),
                    choices=("warn", "strict"),
                    help="正式期遇到验证期数据：warn=继续运行并提醒（默认，不强制转档）/ strict=拒绝")
    args = ap.parse_args()
    cfg.update({"seed": args.seed, "port": args.port, "bind": args.bind,
                "mode": args.mode, "mode_policy": args.mode_policy})

    try:
        session = Session(args.seed, mode=args.mode, policy=args.mode_policy)
    except RuntimeError as e:
        print(f"[server] {e}")
        return
    if session.warning:
        print(f"[server] {session.warning}")
    server = ThreadingHTTPServer((args.bind, args.port), make_handler(session, cfg))
    print(f"[server] Moshi 在线（seed={session.seed}，{session.she.age} 岁）：")
    print(f"  OpenAI 兼容 : http://{args.bind}:{args.port}/v1/chat/completions")
    print(f"  OneBot v11  : http://{args.bind}:{args.port}/onebot")
    print(f"  主动(tick)   : POST /tick   （QQ 推送需 service.json 配 onebot_api + qq_user_id）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.save()
        server.server_close()


if __name__ == "__main__":
    main()
