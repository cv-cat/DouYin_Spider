# coding=utf-8
import json
import os
import sys
from loguru import logger

from dy_apis.douyin_api import DouyinAPI
from utils.common_util import init
from utils.data_util import handle_work_info, download_work, save_to_xlsx


class Data_Spider():
    def __init__(self):
        self.douyin_apis = DouyinAPI()

    def spider_work(self, auth, work_url: str, proxies=None):
        """
        爬取一个作品的信息
        :param auth : 用户认证信息
        :param work_url: 作品链接
        :return:
        """
        res_json = self.douyin_apis.get_work_info(auth, work_url)
        data = res_json['aweme_detail']

        work_info = handle_work_info(data)
        logger.info(f'爬取作品信息 {work_url}')
        return work_info

    def spider_some_work(self, auth, works: list, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        爬取一些作品的信息
        :param auth: 用户认证信息
        :param works: 作品链接列表
        :param base_path: 保存路径
        :param save_choice: 保存方式 all: 保存所有的信息, media: 保存视频和图片（media-video只下载视频, media-image只下载图片，media都下载）, excel: 保存到excel
        :param excel_name: excel文件名
        :return:
        """
        if (save_choice == 'all' or save_choice == 'excel') and excel_name == '':
            raise ValueError('excel_name 不能为空')
        work_list = []
        for work_url in works:
            work_info = self.spider_work(auth, work_url)
            work_list.append(work_info)
        for work_info in work_list:
            if save_choice == 'all' or 'media' in save_choice:
                download_work(auth, work_info, base_path['media'], save_choice)
        if save_choice == 'all' or save_choice == 'excel':
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))
            save_to_xlsx(work_list, file_path)


    def spider_user_all_work(self, auth, user_url: str, base_path: dict, save_choice: str, excel_name: str = '', proxies=None):
        """
        爬取一个用户的所有作品
        :param auth: 用户认证信息
        :param user_url: 用户链接
        :param base_path: 保存路径
        :param save_choice: 保存方式 all: 保存所有的信息, media: 保存视频和图片（media-video只下载视频, media-image只下载图片，media都下载）, excel: 保存到excel
        :param excel_name: excel文件名
        :param proxies: 代理
        :return:
        """
        user_info = self.douyin_apis.get_user_info(auth, user_url)
        work_list = self.douyin_apis.get_user_all_work_info(auth, user_url)
        work_info_list = []
        logger.info(f'用户 {user_url} 作品数量: {len(work_list)}')
        if save_choice == 'all' or save_choice == 'excel':
            excel_name = user_url.split('/')[-1].split('?')[0]

        for work_info in work_list:
            work_info['author'].update(user_info['user'])
            work_info = handle_work_info(work_info)
            work_info_list.append(work_info)
            logger.info(f'爬取作品信息 {work_info["work_url"]}')
            if save_choice == 'all' or 'media' in save_choice:
                download_work(auth, work_info, base_path['media'], save_choice)
        if save_choice == 'all' or save_choice == 'excel':
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))
            save_to_xlsx(work_info_list, file_path)

    def spider_some_search_work(self, auth, query: str, require_num: int, base_path: dict, save_choice: str,  sort_type: str, publish_time: str, filter_duration="", search_range="", content_type="",   excel_name: str = '', proxies=None):
        """
            :param auth: DouyinAuth object.
            :param query: 搜索关键字.
            :param require_num: 搜索结果数量.
            :param base_path: 保存路径.
            :param save_choice: 保存方式 all: 保存所有的信息, media: 保存视频和图片（media-video只下载视频, media-image只下载图片，media都下载）, excel: 保存到excel
            :param sort_type: 排序方式 0 综合排序, 1 最多点赞, 2 最新发布.
            :param publish_time: 发布时间 0 不限, 1 一天内, 7 一周内, 180 半年内.
            :param filter_duration: 视频时长 空字符串 不限, 0-1 一分钟内, 1-5 1-5分钟内, 5-10000 5分钟以上
            :param search_range: 搜索范围 0 不限, 1 最近看过, 2 还未看过, 3 关注的人
            :param content_type: 内容形式 0 不限, 1 视频, 2 图文
            :param excel_name: excel文件名
        """
        work_info_list = []
        work_list = self.douyin_apis.search_some_general_work(auth, query, require_num, sort_type, publish_time, filter_duration, search_range, content_type)
        logger.info(f'搜索关键词 {query} 作品数量: {len(work_list)}')
        if save_choice == 'all' or save_choice == 'excel':
            excel_name = query
        for work_info in work_list:
            logger.info(json.dumps(work_info))
            logger.info(f'爬取作品信息 https://www.douyin.com/video/{work_info["aweme_info"]["aweme_id"]}')
            work_info = handle_work_info(work_info['aweme_info'])
            work_info_list.append(work_info)
            if save_choice == 'all' or 'media' in save_choice:
                download_work(auth, work_info, base_path['media'], save_choice)
        if save_choice == 'all' or save_choice == 'excel':
            file_path = os.path.abspath(os.path.join(base_path['excel'], f'{excel_name}.xlsx'))
            save_to_xlsx(work_info_list, file_path)

if __name__ == '__main__':
    """
        此文件为爬虫的入口文件，可以直接运行
        dy_apis/douyin_apis.py 为爬虫的api文件，包含抖音的全部数据接口，可以继续封装
        dy_live/server.py 为监听抖音直播的入口文件，可以直接运行
        感谢star和follow
    """

    # 打印 Docker 运行方案
    logger.info("=" * 80)
    logger.info("🐳 Docker 运行方案:")
    logger.info("=" * 80)
    logger.info("1. 运行 Docker 容器:")
    logger.info("   docker run --rm -it \\")
    logger.info("     -v \"$((Resolve-Path .\\datas).Path):/app/datas\" \\")
    logger.info("     -e DY_COOKIES=\"$env:DY_COOKIES\" \\")
    logger.info("     -e DOUYIN_WORKS=\"$env:DOUYIN_WORKS\" \\")
    logger.info("     -e DOUYIN_USER_URL=\"$env:DOUYIN_USER_URL\" \\")
    logger.info("     douyin-spider:local")
    logger.info("=" * 80)
    logger.info("")

    auth, base_path = init()

    data_spider = Data_Spider()
    # save_choice: all: 保存所有的信息, media: 保存视频和图片（media-video只下载视频, media-image只下载图片，media都下载）, excel: 保存到excel
    # save_choice 为 excel 或者 all 时，excel_name 不能为空


    # 1 爬取列表的所有作品信息 作品链接 从环境变量获取
    works_env = os.getenv('DOUYIN_WORKS', '')
    works = []
    if works_env:
        works = [url.strip() for url in works_env.split(',') if url.strip()]
    
    # 2 爬取用户的所有作品信息 用户链接 从环境变量获取
    user_url = os.getenv('DOUYIN_USER_URL', '')
    
    # 检查环境变量是否为空
    if not works and not user_url:
        logger.error("环境变量 DOUYIN_WORKS 和 DOUYIN_USER_URL 都为空，请设置至少一个环境变量")
        sys.exit(1)
    
    # 如果works不为空，则爬取作品列表
    if works:
        data_spider.spider_some_work(auth, works, base_path, 'all', 'test')
    
    # 如果user_url不为空，则爬取用户所有作品
    if user_url:
        data_spider.spider_user_all_work(auth, user_url, base_path, 'all')

    # 3 搜索指定关键词的作品
    # query = "榴莲"
    # require_num = 20  # 搜索的数量
    # sort_type = '0'  # 排序方式 0 综合排序, 1 最多点赞, 2 最新发布
    # publish_time = '0'  # 发布时间 0 不限, 1 一天内, 7 一周内, 180 半年内
    # filter_duration = ""  # 视频时长 空字符串 不限, 0-1 一分钟内, 1-5 1-5分钟内, 5-10000 5分钟以上
    # search_range = "0"  # 搜索范围 0 不限, 1 最近看过, 2 还未看过, 3 关注的人
    # content_type = "0"  # 内容形式 0 不限, 1 视频, 2 图文

    # data_spider.spider_some_search_work(auth, query, require_num, base_path, 'all', sort_type, publish_time, filter_duration, search_range, content_type)

