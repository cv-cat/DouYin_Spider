<p align="center">
  <a href="https://github.com/cv-cat/Douyin_Spider" target="_blank" align="center" alt="Go to Douyin_Spider Website">
    <picture>
      <img width="220" src="./author/logo.jpg" alt="Douyin_Spider logo">
    </picture>
  </a>
</p>
<div align="center">
    <a href="https://www.python.org/">
        <img src="https://img.shields.io/badge/python-3.7%2B-blue" alt="Python 3.7+">
    </a>
    <a href="https://nodejs.org/zh-cn/">
        <img src="https://img.shields.io/badge/nodejs-18%2B-blue" alt="NodeJS 18+">
    </a>
</div>

# 🎶DouYin_Spider

**✨ 专业的抖音数据采集与交互解决方案，支持数据爬取、直播间监听、私信收发等功能**

大模型时代，自动化是每个开发者都绕不开的课题。
当你想让 AI Agent 真正落地到抖音——自动处理私信、感知直播间动态、驱动内容互动——第一道墙往往不是模型能力，而是**平台通信能力的缺失**。

本项目做的事很简单：把这道墙拆掉。

**⚠️ 严禁用于发布不良信息、违法内容！本项目仅供学习与技术研究使用，如有侵权请联系作者删除，后果自负。**

## 🌟 功能特性

- ✅ **多维度数据采集**
  - 用户主页信息 / 作品详情
  - 评论区数据（含多级回复）
  - 智能搜索（视频 / 用户 / 直播）
  - 关注 / 粉丝列表
  - 消息通知 / 收藏列表 / 推荐流
- 🎙️ **直播间实时监听**
  - 弹幕消息 / 礼物（含送礼对象）/ 进场 / 关注 / 点赞 / 房间热度
  - 直播间发送弹幕消息
  - 直播间点赞
- 💬 **抖音私信收发**
  - WebSocket 实时接收私信（文本 / 表情包 / 语音 / 图片 / 分享视频）
  - 主动发送私信
  - 创建 / 查询会话列表
- 🤝 **互动操作**
  - 点赞视频
  - 发布评论 / 回复评论
  - 收藏 / 移动 / 取消收藏作品
- 🚀 **高性能架构**
  - 自动重试机制 / 断线重连
- 🔒 **安全稳定**
  - 抖音最新 API 适配
  - 异常处理机制
  - proxy 代理
- 🎨 **便捷管理**
  - 结构化目录存储
  - 格式化输出（JSON / EXCEL / MEDIA）

## 🎨效果图
### 处理后的所有用户
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/3f3ff858-c443-4a68-bae6-1d16ef43011d)
### 某个用户所有的视频\图集
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/fa6f5e65-7e3c-4abf-b140-cd20c33d3b43)
### 某个视频\图集具体的内容
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/16cfc027-6186-4914-bca4-901f886a9b82)
### 某个直播时的具体弹幕发言和礼物数据
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/e2cde1f1-6309-44fe-8aa3-bca2821bf30d)
### 保存的excel
![image](https://github.com/user-attachments/assets/5dfd8fb4-7597-4f54-af6a-9ab8ba766b7c)



## 🛠️ 快速开始
### ⛳运行环境
- Python 3.7+
- Node.js 18+

### 🎯安装依赖
```
pip install -r requirements.txt
npm install
```

### 🎨配置文件
这里以小红书的cookie获取为例

注意.env文件有两个变量，一个是打开www.douyin.com这个域名获取的，另一个是打开live.douyin.com这个域名获取的，第一个用于爬虫，第二个用于直播间监听

配置文件在项目根目录.env文件中，将下图自己的登录cookie放入其中，cookie获取➡️在浏览器f12打开控制台，点击网络，点击fetch，找一个接口点开
![image](https://github.com/user-attachments/assets/6a7e4ecb-0432-4581-890a-577e0eae463d)

复制cookie到.env文件中（注意！登录抖音后的cookie才是有效的，不登陆没有用）
![image](https://github.com/user-attachments/assets/60291f3f-9b69-423f-8b11-167278d44639)



### 🚀运行项目
```
# 数据爬取
python main.py

# 直播间监听（弹幕 / 礼物 / 点赞等）
python dy_live/server.py

# 抖音私信实时接收
python dy_apis/douyin_recv_msg.py
```

### 🗝️注意事项
- `main.py` 是爬虫入口，可根据需求自行修改调用
- `dy_apis/douyin_api.py` 包含全部 API 接口封装，含直播间点赞、发消息、私信收发等
- `dy_live/server.py` 包含直播间 WebSocket 监听逻辑
- `dy_apis/douyin_recv_msg.py` 包含抖音私信 WebSocket 实时接收逻辑


## 🍥日志
   
| 日期       | 说明                                   |
| -------- | ------------------------------------ |
| 23/10/05 | - 项目完成。 |
| 23/10/17 | - 首次提交。 |
| 23/10/18 | - 监听直播间弹幕和礼物。 |
| 23/10/21 | - 新增搜索智能排序和限制时间。 |
| 23/10/21 | - 新增可视化界面到release v1.1.0。 |
| 23/10/25 | - 新增issue提出的输出直播间消息时包括用户等级。 |
| 23/10/28 | - 遇到验证码请手动点击！Fix Some Bugs。 |
| 23/11/11 | - 修复了很多很多大家的bug~~，关于v.dy格式的url正在处理 |
| 23/12/22 | - 修复了直播间监控 |
| 25/06/07 | - 开放所有之前闭源的代码，包括数据爬取和直播间监听 |
| 26/04/09 | - 修复直播间礼物信息接收（含送礼对象）；新增直播间点赞、直播间发弹幕；新增抖音私信实时接收（WebSocket）与主动发送功能 |

## 🤝 欢迎贡献 PR

本项目欢迎任何形式的贡献！如果你有新功能想法、Bug 修复或文档改进，欢迎提交 PR。

- Fork 本仓库并在新分支上开发
- 保持代码风格与现有代码一致
- PR 描述中请简要说明改动内容和目的
- 也欢迎通过 [Issue](https://github.com/cv-cat/DouYin_Spider/issues) 提出建议或报告问题

## 🧸额外说明
1. 感谢star⭐和follow📰！不时更新
2. 作者的联系方式在主页里，有问题可以随时联系我
3. 可以关注下作者的其他项目，欢迎 PR 和 issue
4. 感谢赞助！如果此项目对您有帮助，请作者喝一杯奶茶~~ （开心一整天😊😊）
5. thank you~~~

<div align="center">
  <img src="./author/wx_pay.png" width="400px" alt="微信赞赏码"> 
  <img src="./author/zfb_pay.jpg" width="400px" alt="支付宝收款码">
</div>


## 📈 Star 趋势
<a href="https://www.star-history.com/#cv-cat/DouYin_Spider&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=cv-cat/DouYin_Spider&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=cv-cat/DouYin_Spider&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=cv-cat/DouYin_Spider&type=Date" />
 </picture>
</a>


## 🍔 交流群
如果你对爬虫和ai agent感兴趣，请加作者主页wx通过邀请加入群聊

ps: 请加群7，人满或者过期 issue | wx 提醒

![group7](https://github.com/cv-cat/Spider_XHS/blob/master/author/group7.jpg)





