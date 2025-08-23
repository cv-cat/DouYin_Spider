<p align="center">
  <a href="https://github.com/cv-cat/Spider_XHS" target="_blank" align="center" alt="Go to XHS_Spider Website">
    <picture>
      <img width="220" src="https://github.com/user-attachments/assets/0c53df4f-5c5d-4e21-a086-f4ebf8b571a0" alt="Spider_XHS logo">
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

**✨ 专业的抖音数据采集解决方案，支持笔记爬取，保存格式为excel或者media**

**⚠️ 任何涉及数据注入的操作都是不被允许的，本项目仅供学习交流使用，如有违反，后果自负**

## 🌟 功能特性

- ✅ **多维度数据采集**
  - 用户主页信息
  - 笔记详细内容
  - 智能搜索结果抓取
- 🚀 **高性能架构**
  - 自动重试机制
- 🔒 **安全稳定**
  - 抖音最新API适配
  - 异常处理机制
  - proxy代理
- 🎨 **便捷管理**
  - 结构化目录存储
  - 格式化输出（JSON/EXCEL/MEDIA）

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
python main.py
python dy_live/server.py
```

### 🚀docker 运行项目

```
# 项目根目录下
docker build -t douyin-spider:local .
```
```powershell
# 修改完.env 和main.py后
docker run --rm -it `
  -v "$((Resolve-Path .\.env).Path):/app/.env" `
  -v "$((Resolve-Path .\main.py).Path):/app/main.py" `
  -v "$((Resolve-Path .\datas).Path):/app/datas" `
  douyin-spider:local
```

### 🗝️注意事项
- main.py中的代码是爬虫的入口，可以根据自己的需求进行修改
- dy_apis/douyin_apis.py 中的代码包含了所有的api接口，可以根据自己的需求进行修改
- dy_live/server.py 中的代码包含了直播间监听的接口，可以根据自己的需求进行修改


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
## Star History


