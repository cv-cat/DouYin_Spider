import subprocess
import threading

from pojo.server import Server

# 1.查看指定端口的占用情况
# netstat -aon|findstr "9999"
# 2 .直接强制杀死指定端口
# taskkill /pid 4136 -t -f
def start_new_client(url, port, shell=True):
    client_cmd_string = f'python .\pojo\client.py --url {url} --port {port}'
    subprocess.Popen(client_cmd_string, shell=shell,  creationflags=subprocess.CREATE_NEW_CONSOLE)

if __name__ == '__main__':
    port = 9999
    # server_cmd_string = f'python .\server.py --port {port}'
    # subprocess.Popen(server_cmd_string, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

    # dy_server = Server(port=port)
    # dy_server.main()

    dy_server = Server(port=port)
    thread = threading.Thread(target=dy_server.main)
    thread.start()

    url_1 = 'https://live.douyin.com/29691503928'
    start_new_client(url_1, port)

    # url_2 = 'https://live.douyin.com/31267501116'
    # start_new_client(url_2, port)

    thread.join()