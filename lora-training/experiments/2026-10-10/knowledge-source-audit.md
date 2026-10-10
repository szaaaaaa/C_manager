# 冻结用途资料的来源复核

2026-10-10复核。实验输入 `inputs/knowledge.json` 不修改；本页只登记官方页面当前可读取的支持范围与检索限制。严格资料忠实性是对冻结事实的忠实程度，不能自动等同于现实文件用途准确率。

| 条目 | 核对的官方来源 | 支持范围及边界 |
|---|---|---|
| WebView2 | [Microsoft：分发WebView2 Runtime](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution) | 生产应用使用Runtime，与Edge浏览器依赖分开；页面也提到符合条件时二者可能硬链接。逻辑独立不等于任何文件完全物理独立，来源没有验证本机某版本目录可删。 |
| OneNote | [Microsoft：同步问题](https://support.microsoft.com/en-us/onenote/onenote-help-and-learning/fix-issues-when-you-can-t-sync-onenote) | 页面要求备份未同步的近期笔记，并提醒部分重置/重装操作有数据丢失风险。没有逐文件证明本轮合成cache路径的实际内容；本地缓存和云端缺失的具体删除后果仍是条件性判断。 |
| pip缓存 | [pip：Caching](https://pip.pypa.io/en/stable/topics/caching/) | 缓存用于下载响应/构建wheel，后续安装可复用；purge清理HTTP与wheel缓存，不能推成每次运行已安装软件都要重新下载。具体缓存结构属于可能变化的实现细节。 |
| PyTorch | [PyTorch主分支文档](https://docs.pytorch.org/docs/main/index.html) | 支持张量计算与机器学习库的通用用途。冻结来源入口 `/docs/stable/` 在本次读取仅返回重定向；包内DLL损坏影响依赖是条件性工程判断，未在用户环境执行删除验证。主分支文档版本不用于替换本轮固定Torch运行版本。 |
| Hugging Face缓存 | [HF：Understand caching](https://huggingface.co/docs/huggingface_hub/guides/manage-cache) | 支持模型/数据资源缓存及缺文件时离线下载失败。不能据资源文件名猜任务，也不能从可重新下载推成用户没有本地修改或删除永远无损失。 |
| Node依赖 | [npm：npm-install](https://docs.npmjs.com/cli/v11/commands/npm-install/) | 支持安装到node_modules及声明/锁文件控制重装；手工修改能否恢复与项目是否仍依赖，需要另行确认。 |
| 用户与Windows临时目录 | [Microsoft：Free up drive space](https://support.microsoft.com/en-us/windows/experience/storage-filemanagement/free-up-drive-space-in-windows) | 支持通过Storage/Cleanup recommendations审阅并清理临时文件。冻结的旧短URL本次浏览读取返回Internal Error，不能据此判定HTTP404；已找到同名官方新路径。当前来源没有逐文件确认两个Temp样例是否被占用。 |

以上没有读取用户实际文件、运行清理或验证删除恢复。备份、使用中跳过、依赖确认等防护是保守操作条件；不能把文档一般用途直接当作每个匹配路径已经核实。后续知识库若更新来源URL或事实，应建立新版本并重跑，不能修改本轮冻结输入后继续沿用原分数。
