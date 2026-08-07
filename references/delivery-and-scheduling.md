# 推送与调度

## 强制初始化门禁

即使 `config.yaml` 中存在默认值，也绝不能直接开始采集。默认值只是草稿，不是用户同意。

首次采集前，应逐次询问一个问题，并用 `configure --set` 将每个回答写入 `config.yaml`：

1. 数据源范围与关键来源。
2. 采集时间窗口。
3. 手动或定时模式；若为定时，频率、具体时间、时区和补跑策略。
4. 仅本地存储或需要推送；若启用推送，适配器和每位收件人。
5. Agent 原生模型、仅确定性规则，或兼容 API 模式。
6. 输出目录与保留期限。

然后：

1. 运行 `setup-status`。
2. 展示完整的配置和精确的收件人列表。
3. 获得用户对完整配置的明确确认。
4. 运行 `finalize-setup --confirmed-by-user`。
5. 仅在状态报告 `valid: true` 后，才执行采集。

在任何网络请求之前，`run`、`deliver` 和 `retry-outbox` 必须拒绝过期、不完整、已变更或未确认的配置。

## 推送顺序

1. 手动或 Agent 原生运行时，优先使用 Agent 的 Gmail/Outlook 连接器。
2. 无人值守运行时，使用 HTTPS 邮件 Webhook。
3. 使用应用密码或经授权凭据的 SMTP。
4. 本地 outbox 重试。

运行器不得将 Agent 连接器视为独立 OS 进程可用的资源。

## 首次发送门禁

1. 生成 `digest.txt`。
2. 展示完整的收件人列表和本地预览。
3. 获得用户明确批准。
4. 发送测试消息。
5. 在运行时状态中记录首次发送批准。
6. 后续定时发送无需重复确认。

## 失败语义

- 要求 Webhook 返回 2xx 响应。
- 要求 SMTP 发送完成且无异常。
- 失败时，以摘要 ID 为键创建幂等 outbox 记录。
- 不得重新采集来源来重试邮件。
- 直到某个通道成功之前，不得将摘要标记为已发送。

## 推荐的默认值

以下仅为向用户呈现的建议。未经询问不得将其写为已确认的答案。

- 时区：用户的本地时区。
- 运行时间：20:30。
- 频率：每日。
- 采集窗口：48 小时。
- 补跑：错过运行后最多补跑一次。
- 多个收件人：所有人都收到相同的 V1 摘要。

## 调度器模板

始终先展示生成的调度器命令/配置，征得同意后再安装。

### macOS launchd

使用绝对路径运行 CLI：

```xml
<key>ProgramArguments</key>
<array>
  <string>/absolute/path/to/python3</string>
  <string>/absolute/path/to/healthcare_intelligence.py</string>
  <string>run</string>
  <string>--config</string>
  <string>/absolute/path/to/config.yaml</string>
  <string>--send</string>
</array>
```

使用 `StartCalendarInterval` 设定确认后的小时和分钟。将日志存储于配置的运行时目录内。

### cron

```cron
30 20 * * * /absolute/path/to/python3 /absolute/path/to/healthcare_intelligence.py run --config /absolute/path/to/config.yaml --send
```

### Windows 任务计划程序

创建每日任务，调用绝对路径的 Python 可执行文件，传入脚本及 `run --config ... --send` 参数，将运行时目录设为工作目录。

## 模型访问

- Agent 订阅通常仅可在该 Agent 内部使用。
- 脱离 Agent 的 OS Python 进程不能假定可以访问 Agent 的已登录会话。
- 若无 LLM API，运行器会写入一份确定性规则生成的基础摘要。
- 若有 OpenAI 兼容 API，仅将其用于执行摘要；确定性事件记录和来源链接仍为权威数据。
