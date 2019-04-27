from src.spider.QQZoneSpider import QQZoneSpider
from urllib import parse
import json
import pandas as pd
from src.util import util
from src.util.constant import BASE_DIR
import time
class QQZoneFriendSpider(QQZoneSpider):
    """
    爬取自己的好友的数量等基本信息（不是爬好友的动态）
    """
    def __init__(self, use_redis=False, debug=False, analysis=False, recover=False):
        """

        :param use_redis: 是否使用redis
        :param debug: 是否开启debug模式
        :param analysis: 如果为true, 会执行爬虫程序，再执行分析程序，如果为false，只执行分析程序
        """
        QQZoneSpider.__init__(self, use_redis=use_redis, debug=debug, recover=recover)
        if self.g_tk == 0 and analysis == False:
            self.login()

        FRIEND_DIR_HEAD = BASE_DIR + 'friend/' + self.file_name_head
        self.FRIEND_LIST_FILE_NAME = FRIEND_DIR_HEAD + '_friend_list.json'
        self.FRIEND_DETAIL_FILE_NAME = FRIEND_DIR_HEAD + '_friend_detail.json'
        self.FRIEND_DETAIL_LIST_FILE_NAME = FRIEND_DIR_HEAD + '_friend_detail_list.csv'
        # 头像下载到web的static文件夹，以便在web中调用
        self.FRIEND_HEADER_IMAGE_PATH = '../web/static/image/header/'

        util.check_dir_exist(self.FRIEND_HEADER_IMAGE_PATH)
        self.friend_detail = []
        self.friend_list = []
        self.friend_df = None
        self.re = self.connect_redis()


    def get_friend_list(self):
        """
        获取好友列表信息
        :return:
        """
        friend_list_url = self.get_friend_list_url()
        friend_content = self.get_json(self.req.get(url=friend_list_url, headers=self.headers).content.decode('utf-8'))
        self.friend_list = json.loads(friend_content)['data']['items']
        if self.use_redis:
            self.re.set('friend_list', self.friend_list)
        self.save_data_to_json(self.friend_list, self.FRIEND_LIST_FILE_NAME)
        print('获取好友列表信息完成')

    def download_head_image(self):
        for item in self.friend_list:
            url = item['img']
            print(url)
            name = item['uin']
            self.download_image(url, self.FRIEND_HEADER_IMAGE_PATH + str(name))

    def get_friend_detail(self):
        """
        根据好友列表获取好友详情
        :return:
        """
        self.get_friend_list()
        i = 0
        for friend in self.friend_list:
            uin = friend['uin']
            i = i + 1
            print(i)
            print('正在爬取:', uin, '...')
            url = self.get_friend_detail_url(uin)
            content = self.get_json(self.req.get(url, headers=self.headers).content.decode('utf-8'))
            data = json.loads(content)
            try:
                data = data['data']
            except BaseException as e:
                self.format_error(e, friend)
                print(data)
                continue
            self.friend_detail.append(data)

        if self.use_redis:
            self.re.set(self.FRIEND_DETAIL_FILE_NAME, self.friend_detail)
        self.save_data_to_json(self.friend_detail, self.FRIEND_DETAIL_FILE_NAME)

    def get_friend_list_url(self):
        friend_url = 'https://user.qzone.qq.com/proxy/domain/r.qzone.qq.com/cgi-bin/tfriend/friend_show_qqfriends.cgi?'
        params = {
            'uin': self.username,
            'follow_flag': 0,
            'groupface_flag': 0,
            'fupdate': 1,
            'g_tk': self.g_tk,
            'qzonetoken': ''
        }
        friend_url = friend_url + parse.urlencode(params)
        return friend_url

    def get_friend_detail_url(self, uin):
        detail_url = 'https://user.qzone.qq.com/proxy/domain/r.qzone.qq.com/cgi-bin/friendship/cgi_friendship?'
        params = {
            'activeuin': self.username,
            'passiveuin': uin,
            'situation': 1,
            'isCalendar': 1,
            'g_tk': self.g_tk
        }
        return detail_url + parse.urlencode(params)

    def load_friend_data(self):
        try:
            self.friend_detail = self.re.get(self.FRIEND_DETAIL_FILE_NAME)
            self.friend_list = self.re.get(self.FRIEND_LIST_FILE_NAME)
            if self.friend_detail is None or self.friend_list is None:
                raise BaseException
        except BaseException as e:
            self.format_error(e, "Failed to load data from redis")
            print("try to load data from json now")
            try:
                self.friend_detail = self.load_data_from_json(self.FRIEND_DETAIL_FILE_NAME)
                self.friend_list = self.load_data_from_json(self.FRIEND_LIST_FILE_NAME)
                print("Success to load data from json")
            except BaseException as e:
                self.format_error(e, "Failed to load data from json, Make sure the correct filename")
                exit(1)



    def clean_friend_data(self):
        """
        清洗好友数据，生成csv
        :return:
        """
        if len(self.friend_list) == 0:
            self.load_friend_data()
        friend_total_num = len(self.friend_list)
        print("friend num:", friend_total_num)
        self.user_info.friend_num = friend_total_num
        friend_list_df = pd.DataFrame(self.friend_list)
        self.friend_detail_list = []
        for friend in self.friend_detail:
            try:
                friend_uin = friend['friendUin']
                add_friend_time = friend['addFriendTime']
                img = friend_list_df.loc[friend_list_df['uin'] == friend_uin, 'img'].values[0]
                nick = friend['nick']
                nick_name = nick[str(friend_uin)]
                common_friend_num = len(friend['common']['friend'])
                common_group_num = len(friend['common']['group'])
                common_group_names = friend['common']['group']
                self.friend_detail_list.append(
                    dict(uin=self.username, friend_uin=friend_uin, add_friend_time=add_friend_time,
                         nick_name=nick_name, common_friend_num=common_friend_num,
                         common_group_num=common_group_num, common_group_names=common_group_names, img=img))

            except BaseException as e:
                print("Error in friend list, please check:", friend)
                print(e)
        friend_df = pd.DataFrame(self.friend_detail_list)
        friend_df.sort_values(by='add_friend_time', inplace=True)
        friend_df.to_csv(self.FRIEND_DETAIL_LIST_FILE_NAME)
        print("Finish to clean friend data...")
        print("File Name:", self.FRIEND_DETAIL_LIST_FILE_NAME)
        return friend_df

    def get_friend_total_num(self):
        self.load_friend_data()
        friend_total_num = len(self.friend_list)
        return friend_total_num

    def calculate_friend_num_timeline(self, timestamp, friend_df):
        """
        :param timestamp: 传入时间戳
        :return: 用户在给定时间点的好友数量
        """

        friend_total_num = friend_df.shape[0]
        friend_df_time = friend_df[friend_df['add_friend_time'] > timestamp]
        friend_time_num = friend_total_num - friend_df_time.shape[0]
        if self.debug:
            print(util.get_standard_time_from_mktime(timestamp), friend_time_num)
        return friend_time_num

    def get_friend_result_file_name(self):
        return self.FRIEND_DETAIL_LIST_FILE_NAME

    def get_friend_info(self):
        if self.friend_df is None:
            self.friend_df = pd.read_csv(self.FRIEND_DETAIL_LIST_FILE_NAME)

        zero_index = self.friend_df[self.friend_df['add_friend_time'] == 0].index
        self.friend_df.drop(index=zero_index, axis=0, inplace=True)
        self.friend_df.reset_index(inplace=True)
        early_time = util.get_standard_time_from_mktime(self.friend_df.loc[0,'add_friend_time'])

        early_nick = self.friend_df.loc[0, 'nick_name']
        first_header_url = self.FRIEND_HEADER_IMAGE_PATH + str(int(self.friend_df.loc[0, 'friend_uin'])) + '.jpg'
        self.user_info.first_friend = early_nick
        self.user_info.first_friend_time = early_time
        self.user_info.first_friend_header = first_header_url

        self.user_info.save_user(self.username)


if __name__ == '__main__':
    friend_spider = QQZoneFriendSpider(use_redis=True, debug=True, analysis=False)
    friend_spider.get_friend_detail()
    friend_spider.download_head_image()
    friend_spider.clean_friend_data()
    friend_spider.get_friend_info()
    # friend_spider.calculate_friend_num_timeline(1411891250)
