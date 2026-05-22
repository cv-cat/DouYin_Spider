import os
# from loguru import logger
from dotenv import load_dotenv

dy_auth = None
dy_live_auth = None
def load_env():
    global dy_auth, dy_live_auth
    load_dotenv()
    cookies_dy = os.getenv('DY_COOKIES')
    cookies_live = os.getenv('DY_LIVE_COOKIES')
    
    # 检查 DY_COOKIES 是否为空
    if not cookies_dy:
        raise ValueError("环境变量 DY_COOKIES 为空，请设置有效的抖音cookies")
    
    from builder.auth import DouyinAuth
    dy_auth = DouyinAuth()
    dy_auth.perepare_auth(cookies_dy, "", "")
    dy_live_auth = DouyinAuth()
    dy_live_auth.perepare_auth(cookies_live, "", "")
    return dy_auth

def init():
    media_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/media_datas'))
    excel_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/excel_datas'))
    for base_path in [media_base_path, excel_base_path]:
        if not os.path.exists(base_path):
            os.makedirs(base_path)
            # logger.info(f'create {base_path}')
    cookies = load_env()
    base_path = {
        'media': media_base_path,
        'excel': excel_base_path,
    }
    return cookies, base_path
