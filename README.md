# 🎶DouYin_Spider

抖音，抖音爬虫，抖音视频、图片、主页、搜索、用户信息爬取，抖音直播监控（小红书爬虫在隔壁）

如需定制内容，csv、数据库、WebUI界面等请联系作者


## 🎨效果图
### 处理后的所有用户
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/3f3ff858-c443-4a68-bae6-1d16ef43011d)
### 某个用户所有的视频\图集
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/fa6f5e65-7e3c-4abf-b140-cd20c33d3b43)
### 某个视频\图集具体的内容
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/16cfc027-6186-4914-bca4-901f886a9b82)
### 某个直播时的具体弹幕发言和礼物数据
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/e2cde1f1-6309-44fe-8aa3-bca2821bf30d)
### 图形化界面
![image](https://github.com/cv-cat/DouYin_Spider/assets/94289429/9f44f934-3558-4dca-8ff5-3d1171fc7ef2)


## ⛳运行环境
Python环境>=3.7
NodeJS环境>=14
```
pip install -r requirements.txt
python -m playwright install
```

## 🎯运行方法

```
多用户下载（下载用户列表所有的视频\图集）
python home.py
多笔记下载（下载(视频\图集)列表里所有的(视频\图集)）
python one.py
下载搜索内容
python search.py
监听抖音直播间弹幕 and 礼物
python live.py
```

## 🍥日志
   
| 日期       | 说明                                   |
| -------- | ------------------------------------ |
| 23/10/05 | - 项目完成。 |
| 23/10/17 | - 首次提交。 |
| 23/10/18 | - 监听直播间弹幕和礼物。 |
| 23/10/21 | - 新增搜索智能排序和限制时间。 |
| 23/10/21 | - 新增可视化界面到release v1.1.0。 |


## 🧸注意事项
**本项目仅供学习与交流，侵权必删**

1. home处理的是个人主页 https://www.douyin.com/user/MS4wLjABAAAAEpmH344CkCw2M58T33Q8TuFpdvJsOyaZcbWxAMc6H03wOVFf1Ow4mPP94TDUS4Us
2. one处理的是(视频\图集)详细页 https://www.douyin.com/user/MS4wLjABAAAAh7MdVA-UbMYLeO3_zhA_Z-Mrkh8cDwBCU_qQqucnrFE?modal_id=7137966302055894306
3. search处理的是搜索内容

🛹额外说明
1. 感谢star⭐，不时更新。
2. 有问题可以加QQ或者微信交流（[992822653](tencent://message/?uin=992822653&Site=qq&Menu=yes)）
3. 感谢赞助！请作者喝一杯奶茶~~ （开心一整天😊）

![mm_facetoface_collect_qrcode_1696839915907](https://github.com/cv-cat/Spider_XHS/assets/94289429/f8bac4e2-88f1-440c-987a-9803c0a2bbd5)![1696832397](https://github.com/cv-cat/Spider_XHS/assets/94289429/fb7fee7d-7394-4353-b202-165d74a87f54)




