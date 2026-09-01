# config 目录：存放配置

- `secrets.json`：API Key 等秘密。**不要提交到版本库**（建议加入 .gitignore）。
  格式：
  ```json
  {
    "DEEPSEEK_API_KEY": "sk-你的key"
  }
  ```
- 程序读取顺序：`config/secrets.json` → 环境变量 `DEEPSEEK_API_KEY`（后者兜底）。
