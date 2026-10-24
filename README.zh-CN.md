# resume-fixture 中文说明

为下载器提供可重复的本地断点续传故障：首次完整下载被截断、续传时内容和 ETag
发生变化、服务器忽略 Range，以及正常的单区间下载。仅监听 `127.0.0.1`，无需密钥、
输入文件、外部服务或运行时第三方依赖。要求 Python 3.11 及以上。

```sh
git clone https://github.com/KanadeK/resume-fixture.git
cd resume-fixture
python -m pip install .
resume-fixture demo
resume-fixture serve --port 8765 --size 65536 --drop-after 4096
```

`demo` 通过真实本地连接运行四个流程，并用 SHA-256 验证续传或重新下载后的内容。
JSON 中 `passed` 应为 `true`。服务启动时会打印地址；`/manifest.json` 提供两种内容的
哈希和 ETag。首次完整 GET 才消耗故障，HEAD 和成功的局部探测不会消耗。

接口：`/stable.bin` 正常续传，`/drop-once.bin` 截断一次后保持内容，`/changed.bin`
截断一次后切换内容，`/ignore-range.bin` 始终返回完整 200，`/stats.json` 提供计数。
旧 If-Range 收到 200 时，客户端应替换已有片段。保持服务运行后再重试，重启会重置故障。

当前为 0.1.0：只覆盖文档明确列出的 HTTP/1.1 GET/HEAD、单区间和 ETag 条件；
不模拟 TLS、HTTP/2、多区间、日期验证或带宽。所有连接会关闭。大小上限 64 MiB。
其他本地进程可能提前消耗故障，因此每次测试应使用独立实例。

退出码：演示通过 `0`，校验失败 `1`，配置错误 `2`。Ctrl+C 停止服务；
`python -m pip uninstall resume-fixture` 卸载。不会安装后台服务或创建用户数据文件。
完整协议边界见 [英文 README](README.md) 和 [设计说明](docs/design.md)。
