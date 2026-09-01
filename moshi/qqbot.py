"""QQ 官方机器人适配器（qqbot）—— 她在 QQ 里（官方通道：零封号风险，支持单独对话 C2C）。

依赖：`pip install qq-botpy`（QQ 官方 Python SDK；本项目的唯一第三方依赖，其余全标准库）。
运行：
  python -m moshi.qqbot                  # 正式连接
  python -m moshi.qqbot --seed 12345678  # 指定种子
  python -m moshi.qqbot --sandbox        # 沙箱环境（仅测试/开发）
配置：config/secrets.json → QQ_APPID / QQ_APP_SECRET / DEEPSEEK_API_KEY（均可环境变量兜底）。
控制台（QQ开放平台 → 机器人 → 开发设置）：填好 AppID/AppSecret；消息订阅里开启「私聊消息」（C2C）+「群聊@消息」。
程序用 WebSocket 长连接（无需公网 IP、无需服务器——本地可跑）。

事件 → Session（同一条"她"）：
- 私聊（C2C）：你对她说的每句话；
- 群聊：仅 @她 时回应（不打扰群里其他人）。
主动（她会突然想起你）：每 --tick-minutes 分钟调 session.tick()，若她有话说 → 私聊推送（给她最近对话过的人）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import botpy
from botpy.message import C2CMessage, GroupMessage

from .runtime import Session
from . import voice as voice_mod

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "secrets.json"

# 群消息里的 "被@" 标记（<@!xxxx> / <@xxxx>）
_MENTION_RE = re.compile(r"<@!?\d+(?:\.\d+)?>")


class _VoiceHandler(SimpleHTTPRequestHandler):
    """语音文件服务：把 /voice/<file> 映射到 CACHE_DIR/<file>（QQ 端拉取路径与本地目录解耦）。"""

    def translate_path(self, path: str) -> str:
        path = (path or "").split("?", 1)[0]
        if path.startswith("/voice/"):
            path = path[len("/voice/"):]           # /voice/x.silk → /x.silk
        return super().translate_path("/" + path)


# 对方明确要她"说话"（语音请求）：直接发语音，不走"她选"的决策
_VOICE_REQUEST_WORDS = ("发语音", "发一条语音", "发个语音", "发一段语音", "发条语音",
                        "说句话", "说两句", "听听你的声音", "你的声音", "语音消息", "说给我听")


def _secret(name: str) -> str:
    """读取密钥：环境变量优先，config/secrets.json 兜底。"""
    env = os.environ.get(name, "")
    if env:
        return env.strip()
    try:
        if _CONFIG_PATH.exists():
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            v = (data.get(name) or "").strip()
            if v and not v.startswith("在此"):
                return v
    except Exception:
        pass
    return ""


def _clean(text: str) -> str:
    """消息清洗：去掉 @ 标记与首尾空白（群聊里 @她 的部分不算她收的话）。"""
    return (_MENTION_RE.sub("", text or "")).strip()


class MoshiQQ(botpy.Client):
    """官方 QQBOT：消息 → Session（同一条她）→ 回复（文字或语音——她选）。"""

    def __init__(self, session: Session, tick_minutes: int = 45,
                 voice: bool = True, voice_url_base: str = "http://127.0.0.1:8902",
                 voice_design: str = voice_mod.VOICE_DESIGN_DEFAULT,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self.tick_minutes = tick_minutes
        self.voice = voice
        self.voice_design = voice_design
        self.voice_url_base = voice_url_base.rstrip("/")
        self.last_openid: str | None = None   # 最近和她对话过的用户（主动推送目标）
        self._lock = asyncio.Lock()
        self._tick_task: asyncio.Task | None = None
        self._voice_server = None             # 语音文件 HTTP 服务（QQ 那边拉取 silk 用）

    async def on_ready(self) -> None:
        print(f"[qqbot] 已连接。她是 {self.session.she.age} 岁的陈默识（seed={self.session.seed}）。")
        if self.voice:
            self._start_voice_server()
            print(f"[qqbot] 她可以说话：{voice_mod.describe_voice()}"
                  f"（语音文件服务 {self.voice_url_base}/voice/ —— QQ 需能访问该地址）")
        if self.tick_minutes > 0:
            self._tick_task = asyncio.create_task(self._tick_loop())

    def _start_voice_server(self) -> None:
        """把 data/voice_cache/ 挂到 HTTP（QQ 官方接口拉取媒体文件用）。"""
        try:
            vc = voice_mod.CACHE_DIR
            vc.mkdir(parents=True, exist_ok=True)
            host, port = "0.0.0.0", 8902
            try:
                port = int(self.voice_url_base.split(":")[-1].split("/")[0])
            except Exception:
                pass
            handler = lambda *a, **k: _VoiceHandler(*a, directory=str(vc), **k)
            self._voice_server = ThreadingHTTPServer((host, port), handler)
            import threading
            threading.Thread(target=self._voice_server.serve_forever, daemon=True).start()
        except Exception as e:
            print(f"[qqbot] 语音文件服务启动失败：{e}")

    # ── 私聊（单独对话）──
    async def on_c2c_message_create(self, message: C2CMessage) -> None:
        self.last_openid = message.author.user_openid
        await self._handle(message, _clean(message.content))

    # ── 群聊（仅 @她 时回应）──
    async def on_group_at_message_create(self, message: GroupMessage) -> None:
        if "<@!" not in (message.content or "") and not _MENTION_RE.search(message.content or ""):
            return
        await self._handle(message, _clean(message.content))

    async def _handle(self, message, text: str) -> None:
        if not text:
            return
        async with self._lock:                        # 一次只处理一句（她的状态是连续的）
            out = await asyncio.to_thread(self.session.on_message, text)
        reply = (out.get("reply") or "……").strip()
        await asyncio.sleep(random.uniform(0.8, 3.0))  # 真人打字节奏（消息不是秒回的）
        # ── 明确要语音 → 她直接发语音（系统发；不走"她选"，也绝不让文字冒充语音）──
        if self.voice and any(w in text for w in _VOICE_REQUEST_WORDS):
            try:
                await self._send_voice(message, reply[:60])
                return
            except Exception as e:
                print(f"[qqbot] 语音发送失败：{e}")
                try:
                    await message.reply(content="……语音我这边发不出去，先这样吧。")
                except Exception:
                    pass
                return
        # ── 她选：这轮发文字还是发语音（像真人；语音=仅有语音，不带文字）──
        if self.voice and voice_mod.decide_voice(self.session.she, "chat", reply):
            try:
                await self._send_voice(message, reply)
                return
            except Exception as e:
                print(f"[qqbot] 语音发送失败，降级文字：{e}")
        try:
            await message.reply(content=reply)
        except Exception as e:
            print(f"[qqbot] 回复失败：{e}")

    async def _send_voice(self, message, text: str) -> None:
        """发语音（silk）—— 官方 file_type=3。QQ 服务端需能访问 voice_url_base。"""
        silk = await asyncio.to_thread(voice_mod.ensure_silk, text, self.voice_design)
        url = f"{self.voice_url_base}/voice/{silk.name}"
        if hasattr(message, "group_openid") and message.group_openid:
            await self.api.post_group_file(group_openid=message.group_openid,
                                           file_type=3, url=url, srv_send_msg=True)
        else:
            await self.api.post_c2c_file(openid=message.author.user_openid,
                                         file_type=3, url=url, srv_send_msg=True)
        print(f"[qqbot] 她发语音了：{text[:30]}…")

    # ── 主动：她会突然想起你（低频；经官方接口私聊推送）──
    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_minutes * 60)
            try:
                text = await asyncio.to_thread(self.session.tick)
                if text and self.last_openid:
                    if self.voice and voice_mod.decide_voice(self.session.she, "chat",
                                                             text, turn_kind="touch"):
                        silk = await asyncio.to_thread(voice_mod.ensure_silk, text, self.voice_design)
                        url = f"{self.voice_url_base}/voice/{silk.name}"
                        await self.api.post_c2c_file(openid=self.last_openid,
                                                     file_type=3, url=url, srv_send_msg=True)
                        print(f"[qqbot] 她想你了（语音）：{text[:30]}…")
                    else:
                        await self.api.post_c2c_message(
                            openid=self.last_openid, msg_type=0, content=text)
                        print(f"[qqbot] 她想你了：{text[:40]}…")
            except Exception as e:
                print(f"[qqbot] tick 失败：{e}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Moshi · QQ 官方机器人（她住在 QQ 里）")
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--tick-minutes", type=int, default=45,
                    help="她主动找你的间隔（分钟；0=关闭）")
    ap.add_argument("--sandbox", action="store_true", help="沙箱环境（仅测试）")
    ap.add_argument("--mode", default="verify", choices=("verify", "production"),
                    help="运行标签（verify=验证期 / production=正式期）")
    ap.add_argument("--mode-policy", default="warn", choices=("warn", "strict"),
                    help="正式期遇到验证期数据：warn=继续运行并提醒（默认，不强制转档）/ strict=拒绝")
    ap.add_argument("--no-voice", action="store_true", help="关闭语音（她只说文字）")
    ap.add_argument("--voice-url-base", default="http://127.0.0.1:8902",
                    help="QQ 服务端拉取语音文件的地址（公网可访问；云端部署时改）")
    ap.add_argument("--voice-design", default=voice_mod.VOICE_DESIGN_DEFAULT,
                    choices=tuple(voice_mod.VOICE_DESIGNS),
                    help="音色候选（先 python -m moshi.voice_test 试听再定；默认 A）")
    args = ap.parse_args()

    appid, secret = _secret("QQ_APPID"), _secret("QQ_APP_SECRET")
    if not appid or not secret:
        print("[qqbot] 缺少密钥：在 config/secrets.json 填 QQ_APPID / QQ_APP_SECRET")
        print("        （QQ开放平台 → 机器人 → 开发设置 里获取；不要提交到版本库）")
        return

    try:
        session = Session(args.seed, mode=args.mode, policy=args.mode_policy)
    except RuntimeError as e:
        print(f"[qqbot] {e}")
        return
    # Python >=3.10 不再自动创建事件循环；botpy 的 __init__ 依赖 get_event_loop() → 先挂好
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    client = MoshiQQ(
        session=session,
        tick_minutes=args.tick_minutes,
        voice=not args.no_voice,
        voice_url_base=args.voice_url_base,
        voice_design=args.voice_design,
        intents=botpy.Intents(public_messages=True, public_guild_messages=True),
        is_sandbox=args.sandbox,
    )
    print(f"[qqbot] 启动（seed={args.seed}）…")
    client.run(appid=appid, secret=secret)


if __name__ == "__main__":
    main()
