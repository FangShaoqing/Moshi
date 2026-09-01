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
import re
from pathlib import Path

import botpy
from botpy.message import C2CMessage, GroupMessage

from .runtime import Session

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "secrets.json"

# 群消息里的 "被@" 标记（<@!xxxx> / <@xxxx>）
_MENTION_RE = re.compile(r"<@!?\d+(?:\.\d+)?>")


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
    """官方 QQBOT：消息 → Session（同一条她）→ 回复。"""

    def __init__(self, session: Session, tick_minutes: int = 45, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session
        self.tick_minutes = tick_minutes
        self.last_openid: str | None = None   # 最近和她对话过的用户（主动推送目标）
        self._lock = asyncio.Lock()
        self._tick_task: asyncio.Task | None = None

    async def on_ready(self) -> None:
        print(f"[qqbot] 已连接。她是 {self.session.she.age} 岁的陈默识（seed={self.session.seed}）。")
        if self.tick_minutes > 0:
            self._tick_task = asyncio.create_task(self._tick_loop())

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
        try:
            await message.reply(content=reply)
        except Exception as e:
            print(f"[qqbot] 回复失败：{e}")

    # ── 主动：她会突然想起你（低频；经官方接口私聊推送）──
    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_minutes * 60)
            try:
                text = await asyncio.to_thread(self.session.tick)
                if text and self.last_openid:
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
    client = MoshiQQ(
        session=session,
        tick_minutes=args.tick_minutes,
        intents=botpy.Intents(public_messages=True, public_guild_messages=True),
        is_sandbox=args.sandbox,
    )
    print(f"[qqbot] 启动（seed={args.seed}）…")
    client.run(appid=appid, secret=secret)


if __name__ == "__main__":
    main()
