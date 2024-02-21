class User_Detail():
    def __init__(self, id, sec_uid, nickname, author_avatar, desc, following_count, follower_count, total_favorited, aweme_count, unique_id, user_age, gender, ip_location):
        self.id = id
        self.sec_uid = sec_uid
        self.nickname = nickname
        self.author_avatar = author_avatar
        self.desc = desc
        self.following_count = following_count
        self.follower_count = follower_count
        self.total_favorited = total_favorited
        self.aweme_count = aweme_count
        self.unique_id = unique_id
        self.user_age = user_age
        self.gender = gender
        self.ip_location = ip_location

    def __str__(self):
        # 每个值都要换行 
        return f'id: {self.id}\n' \
                f'sec_uid: {self.sec_uid}\n' \
                f'nickname: {self.nickname}\n' \
                f'author_avatar: {self.author_avatar}\n' \
                f'desc: {self.desc}\n' \
                f'following_count: {self.following_count}\n' \
                f'follower_count: {self.follower_count}\n' \
                f'total_favorited: {self.total_favorited}\n' \
                f'aweme_count: {self.aweme_count}\n' \
                f'unique_id: {self.unique_id}\n' \
                f'user_age: {self.user_age}\n' \
                f'gender: {self.gender}\n' \
                f'ip_location: {self.ip_location}\n'


