# 电商审批脚本

纯 Python HTTP 会话 + Node.js 轻量 DOM 规则校验，无 Chrome、Playwright 或浏览器引擎。提供本机设置页面、定时审批、会话保活和 Bark 通知。

## 安装

需要 Python 3.10+、Node.js 22+、npm、curl，以及系统时区数据库。

```sh
npm ci
python3 setup.py
```

`setup.py` 初始化私有文件，并从网站下载登录加密依赖，校验固定 SHA-256；下载内容不在本仓库分发。现有配置不会覆盖。

填写 `private/credentials.json` 的 username/password，填写 `private/notification.json` 的 barkKey。文件权限保持 0600，private 目录 0700。不要通过命令行参数传递密码或验证码。

```sh
python3 client.py login
python3 client.py check
python3 -m unittest -q test_client test_runner test_keepalive test_execution
python3 service.py
```

登录通过终端隐藏输入短信验证码。有效会话会复用，保活不能保证网站永不要求重新登录。

## 设置及规则

打开 http://127.0.0.1:18766/ 。配置保存在 `settings.json`，Bark 码单独保存在 private 目录。公开示例默认关闭定时审批和 Bark，启用仅验证模式。确认规则后在设置页启用实际审批。

- 物资、服务的竞价审批与结果确认分别设置。
- 物资竞价检查公开报价、最低价法、包名称及限价；服务竞价额外检查附件。
- 多轮竞价不自动同意；明确无附件的驳回目前仍留人工处理。
- 请购付款与签章流程未迁移，不应启用。
- 单据间隔默认 8 秒；读取请求有有限重试。
- 写请求仅对确定未建立连接的错误重试；响应超时保留不确定记录，停止后续提交，不能删除记录后盲目重试。
- 成功必须同时满足网站审批成功响应及完整待审批列表移除。

私有执行记录用于防重复提交，迁移时应通过可信通道携带。不要在两台机器上同时运行同一账号的审批后台。

## Linux 后台

将项目放到 `~/esgcc-approval-script`，登录成功后：

```sh
mkdir -p ~/.config/systemd/user
cp deploy/esgcc-approval.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now esgcc-approval.service
systemctl --user status esgcc-approval.service
```

若系统 Node 版本较旧，可用 `npm install --prefix ~/.local/share/esgcc-runtime node@22` 安装独立运行时，并在服务 PATH 中加入该目录的 `node_modules/.bin`。

需为该用户启用 systemd linger 才能在注销后常驻。审批按 Asia/Shanghai 时区执行。服务仅绑定 127.0.0.1；远程访问请使用 SSH 本地端口转发（保持本地端口 18766），不直接公开设置接口。

## 隐私边界

Git 忽略实际配置、private、Cookie、状态、日志和依赖目录。仓库只有示例配置；不要添加真实账号、密码、短信验证码、Bark 码、抓取页面或运行记录。不要把完整工作目录打包公开。

`vendor/page-command.js` 为项目既有规则适配；来源信息见同目录 JSON。网页脚本不执行，事件参数只接受字面值。页面结构变化时应重新验证规则。
