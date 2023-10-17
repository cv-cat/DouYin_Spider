
class Video_Detail():
    def __init__(self, id, awemeId, sec_uid, nickname, author_avatar, video_cover, title, desc, digg_count, comment_count, collect_count, share_count, video_addr, images, upload_time):
        self.id = id
        self.awemeId = awemeId
        self.sec_uid = sec_uid
        self.nickname = nickname
        self.author_avatar = author_avatar
        self.video_cover = video_cover
        self.title = title
        self.desc = desc
        self.digg_count = digg_count
        self.comment_count = comment_count
        self.collect_count = collect_count
        self.share_count = share_count
        self.video_addr = video_addr
        self.images = images
        self.upload_time = upload_time

    def __str__(self):
        # 每个值都要换行
        return f'id: {self.id}\n' \
                f'awemeId: {self.awemeId}\n' \
                f'sec_uid: {self.sec_uid}\n' \
                f'nickname: {self.nickname}\n' \
                f'author_avatar: {self.author_avatar}\n' \
                f'video_cover: {self.video_cover}\n' \
                f'title: {self.title}\n' \
                f'desc: {self.desc}\n' \
                f'digg_count: {self.digg_count}\n' \
                f'comment_count: {self.comment_count}\n' \
                f'collect_count: {self.collect_count}\n' \
                f'share_count: {self.share_count}\n' \
                f'video_addr: {self.video_addr}\n' \
                f'images: {self.images}\n' \
                f'upload_time: {self.upload_time}\n'

