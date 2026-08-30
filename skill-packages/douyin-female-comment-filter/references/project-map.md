# 本机项目映射

## 项目17

根目录：`E:\SVN\项目17-DouYin_Spider`

优先复用：

- `collect_ip_comments.py`：评论抓取、主页数据补充入口。
- `scripts/clean_gender_evidence_yaml.py`：昵称和内容男性证据清洗。
- `scripts/clean_douyin_gender_playwright.py`：公开主页性别核验。
- `scripts/finalize_chinese_comments_yml.py`：中文字段和YML格式参考。

运行前必须查看各脚本 `--help` 和当前源码，不假设参数长期不变。

## 桌面工具

`C:\Users\13394\Desktop\抖音主页性别清洗工具`

桌面副本用于人工扫码和有头浏览器观察。项目脚本是版本源；更新后同步桌面副本。

## 登录状态

登录档案仅允许保存在桌面工具的 `browser_profile`。不把 Cookie、Local Storage、登录文件打包进技能，也不写入最终YML。
