# 版本与后台状态

本项目最初针对微信 4.1.15.54 / Build 270134 做过公开资料核查。当时没有找到可直接验证的 OneBot 后台读写适配，因此没有把旧偏移套到该版本。

后续在维护窗口中改用腾讯官方微信 4.1.11.53 / Build 269109，并针对该精确构建完成 Gadget、OneBot、原生文本发送和文件传输助手双向验收。当前项目的可用范围以 README 的兼容性表为准。

公开资料中参考过的项目包括：

- [wechat_chatter](https://github.com/yincongcyincong/wechat_chatter)：OneBot 和 Frida 研究基础。
- [wechat-mac-hook-classic](https://github.com/xiaoguiwucan/wechat-mac-hook-classic)：固定版本和 Mach-O Gadget 部署参考。
- [weixin-macos](https://github.com/Leslielu/weixin-macos)：其他版本配置的交叉研究材料。
- [WeChatTweak](https://github.com/zengtianli/WeChatTweak)：4.1.15 相关版本分析材料，但不是本项目的收发实现。

这些项目的版本文件、偏移或读取能力都不能单独证明另一个微信 Build 可以后台收发。适配新版本需要重新确认 Mach-O UUID、调用参数、消息记录回执和电脑/手机真实结果。
