# config 目录：存放配置

- `secrets.json`：API Key 等秘密。**不要提交到版本库**（已加入 .gitignore）。
  格式：
  ```json
  {
    "DEEPSEEK_API_KEY": "sk-你的key",
    "QQ_APPID": "你的QQ机器人AppID",
    "QQ_APP_SECRET": "你的QQ机器人AppSecret"
  }
  ```
- 程序读取顺序：环境变量 → `config/secrets.json`（优先环境变量）。
  - `DEEPSEEK_API_KEY`：DeepSeek（她的口吻）
  - `QQ_APPID` / `QQ_APP_SECRET`：QQ 开放平台 → 机器人 → 开发设置 里的接入票据
- `service.json`（可选）：HTTP 服务层的运行参数（seed/port/bind/onebot_api/qq_user_id/mode）。
