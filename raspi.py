# -*- coding: utf-8 -*-
# 代码中对应的参数都改成自己的设备参数

import _thread  # 多线程模块
import sys
import Adafruit_DHT
import re  # 正则表达式
import random  # 随机数模块
import time  # 时间模块
import base64  # base64编码解码
import signal  # 处理信号
import os  # 调用系统命令
import urllib3  # 请求url连接
import urllib.request
import requests
import json  # 编码和解码 JSON 对象
import snowboydecoder  # snowboy唤醒
import RPi.GPIO as GPIO  # 控制树莓派GPIO
import aliyunsdkiotclient.AliyunIotMqttClient as iot  # 阿里云平台mqtt连接
from init import Init, Light  # GPIO初始化
from aip import AipSpeech  # 百度语音sdk
from ftplib import FTP  # ftp连接
from MyEncoder import MyEncoder  # 自定义json序列化
from urllib.error import HTTPError, URLError  # URLError与HTTPError的异常处理
from http.client import IncompleteRead, RemoteDisconnected

# 关闭 requests 的 InsecureRequestWarning
urllib3.disable_warnings()
interrupted = False

# 百度云api连接参数
baidu_config = {
    'APP_ID': '183***44',
    'API_KEY': '5zrkKb7HY*****pf2xaC',
    'SECRET_KEY': 'qqm9cm8XpGbcgUr1q5*****E8y9rMGp3P'
}

# 阿里云物联网平台mqtt连接参数
aliyun_config = {
    'productKey': 'a1BV5***5K',
    'deviceName': 'raspi',
    'deviceSecret': 'Dwh9QMO3KrlaO05l*****UTcpJdM',
    'port': 1883,
    'host': 'a1BV5***5K.iot-as-mqtt.cn-shanghai.aliyuncs.com'
}

# mqtt topic
topicHead = '/' + aliyun_config['productKey'] + \
            '/' + aliyun_config['deviceName']
topics = {
    'topic1': topicHead + '/user/setDevice',
    'topic2': topicHead + '/user/sendDHT11',
    'topic3': topicHead + '/user/putHumanMonitor',
    'topic4': topicHead + '/user/putSmokeStatus'
}

# 腾讯云短信接口连接参数  该功能需要申请需要上线的网站or应用  需要该功能的自行了解开启该功能
# shortMessage_config = {
#     'appid': '14***52671',
#     'appkey': 'ad37309184fae22****1c7bf4aaaacd2',
#     'phone_numbers': '130***2736',
#     'template_id': '57**26',
#     'sms_sign': '智能小派家居控制终端'
# }

dht11=[0,0]

# 获取百度云token  client_id和client_secret需要替换成上面baidu_config的API_KEY和SECRET_KEY
def getaccess_token():
    host = 'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id=5zrkKb7HY*****pf2xaC&client_secret=qqm9cm8XpGbcgUr1q5*****E8y9rMGp3P'
    header_1 = {'Content-Type': 'application/json; charset=UTF-8'}
    request = requests.post(host, headers=header_1)
    access_token = request.json()['access_token']
    # print(access_token)
    return access_token


# 在线语音识别  与逻辑处理
def Speech(access_token):
    global detector
    request_url = "http://vop.baidu.com/server_api"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Trident/7.0; rv:11.0) like Gecko',"Content-Type": "application/json"}
    WAVE_FILE = "beginSpeech.wav"
    # begin Speech
    answers = ["我在,请说话.", "来了,来了,我来了!", "您好,老大,我是小派!", "我是机智可爱的小派,有何指示?"]
    baidu_tts(answers[randomNumber(answers)])
    print("小派开始录音了,录音时间3s!")
    os.system(
        'arecord -d 3 -r 16000 -c 1 -t wav -f S16_LE -D plughw:1,0  beginSpeech.wav')  # 采集音频
    print("录音结束,语音识别中...")
    f = open(WAVE_FILE, "rb")  # 以二进制读模式打开输入音频
    speech = base64.b64encode(f.read())  # 读音频文件并使用base64编码
    size = os.path.getsize(WAVE_FILE)  # 获取文件大小(字节)
    data_json = json.dumps(
        {"format": "wav", "rate": 16000, "channel": 1, "cuid": "zhl", "token": access_token,
         "speech": speech, "len": size}, cls=MyEncoder, indent=4)  # 请求数据格式
    try:
        response = requests.post(request_url, data=data_json,
                             headers=headers)  # 发起requests post请求
        print("resJson",response.json())
        resJson = response.json()
        if resJson.get('err_msg') == 'success.':  # 处理返回数据
            words = resJson.get('result')[0]
            print("您说的是:" + words)
            if re.findall('[温湿度]', words):
                temperature, humidity = getDHT11Data()
                words = "老大,室内温度:" + str(temperature) + ",室内湿度:" + str(humidity)
                baidu_tts(words)
            elif re.findall('[天气]', words):
                baidu_tts(str(getWeatherData()))
            elif re.findall('开.*灯', words):
                led1.set_on()
                baidu_tts("老大,灯已打开.")
            elif re.findall('关.*灯', words):
                led1.set_off()
                baidu_tts("老大,灯已关闭.")
            elif re.findall('开.*[风扇]', words):
                fan.set_off()
                baidu_tts("老大,风扇已打开.")
            elif re.findall('关.*[风扇]', words):
                fan.set_on()
                baidu_tts("老大,风扇已关闭.")
            else:
                baidu_tts(tuling(words))
        else:
            baidu_tts("对不起老大,小派没有听清.")
    except Exception as e:
        baidu_tts("对不起老大,小派没有听清.")


# 百度语音合成
def baidu_tts(words):
    result = client.synthesis(words, 'zh', 1, {'vol': 5, 'per': 4})  # 请求参数
    if not isinstance(result, dict):  # 识别正确返回语音二进制 错误则返回dict
        with open('audio.mp3', 'wb') as f:  # wb表示二进制写入
            f.write(result)
        os.system('mplayer audio.mp3')
    else:
        print(result)


# 人脸识别接口请求
def getsearchMessage(img, access_token):
    request_url = "https://aip.baidubce.com/rest/2.0/face/v3/search"
    params = {"image": img, "image_type": "BASE64", "group_id_list": "face_list", "quality_control": "LOW",
              "liveness_control": "NORMAL"}
    request_url = request_url + "?access_token=" + access_token
    response = requests.post(request_url, data=params)
    return response.json()


# 人脸搜索返回处理
def faceSearch(img, access_token):
    output = getsearchMessage(img, access_token)
    if output['error_msg'] == 'SUCCESS':
        user_list = output['result']['user_list']
        print(user_list)
        score = user_list[0]['score']
        user = user_list[0]['user_id']
        # 与百度云新建的用户id一致
        if user == 'zhang***lin':
            words = "认证成功,您是***." + "相似度为百分之" + \
                    str(round(score, 2)) + ",快来唤醒小派吧!"
            baidu_tts(words)
            wake_up()
    else:
        print(output['error_msg'])
        baidu_tts("对不起,认证失败!")


# 图灵机器人智能对话
def tuling(words):
    request_url = "http://openapi.tuling123.com/openapi/api/v2"
    api_key = "e01ee05ea2164b*******ae3274a8"
    headers = {'content-type': 'application/json'}
    request_data = {"userInfo": {"apiKey": api_key, "userId": "zhang***lin"},
                    "perception": {"inputText": {"text": words}}}
    response = requests.post(
        request_url, data=json.dumps(request_data), headers=headers)
    response_text = response.json()["results"][0]["values"]["text"]
    return response_text


# 监控人脸认证
def monitorSearch(img, access_token):
    output = getsearchMessage(img, access_token)
    if output['error_msg'] != 'SUCCESS':
        return 1
    else:
        pass


# 摄像头拍照
def get_picture(num_retries=3):
    # 192.168.137.100改成自己树莓派的ip
    img_url = 'http://192.168.137.100:8080/?action=snapshot'  # 此刻摄像头采集的图片地址
    # Request类可以使用给定的header访问URL
    req = urllib.request.Request(url=img_url)  # 请求访问图片地址
    try:
        response = urllib.request.urlopen(req)  # 请求包装处理
        filename = 'people.jpg'
        with open(filename, "wb") as f:
            content = response.read()  # 获得图片
            f.write(content)  # 保存图片
            response.close()
    except HTTPError as e:  # HTTP响应异常处理
        print(e.reason)
    except URLError as e:  # 一定要放到HTTPError之后，因为它包含了前者
        print(e.reason)
    except IncompleteRead or RemoteDisconnected as e:
        if num_retries == 0:  # 重连机制
            return
        else:
            get_picture(num_retries - 1)
    # 打开图片并转码  rb以二进制格式打开一个文件用于只读
    f = open('people.jpg', 'rb')
    img = base64.b64encode(f.read())
    return img


# 上传FTP服务器 不需要把图片上传服务器的注释了 有需要该功能的开启
# def ftp_upload():
#     ftp = FTP()
#     # 第一个参数可以是ftp服务器的ip或者域名，第二个参数为ftp服务器的连接端口，默认为21
#     ftp.connect("103.40.**.212", 21)
#     ftp.login('root', '123456')  # 匿名登录直接使用ftp.login()
#     ftp.cwd("/resource/images")  # 切换到/resource/images目录
#     fp = open("people.jpg", "rb")  # 打开摄像头采集到的图像
#     ftp.storbinary("STOR {}".format('illegalPerson.jpg'), fp, 1024)  # 上传图像到服务器
#     fp.close()
#     ftp.quit()


# 身份认证
def verify():
    baidu_tts("您好,我是小派,使用小派之前将先对您进行身份认证哦!")
    print("开始认证...")
    img = get_picture()
    faceSearch(img, access_token)


# 热释电红外传感器监控
def humanMonitoring():
    if human.is_on():  # 监测高电平则表示热释电红外传感器监测到异常
        print("监测到有人靠近...开始人脸检测...")
        img = get_picture()  # 摄像头采集图像
        result = monitorSearch(img, access_token)  # 将采集到的图像上传百度云人脸库搜索
        if result == 1:  # 图像搜索不到则表示陌生物体靠近
            led2.blink()  # 红灯警告
            # ftp_upload()  # 上传FTP服务器
            mqttClient.publish(topics['topic3'], json.dumps(
                {"human": 1}), 0)  # 发布MQTT消息到阿里云物联网平台
            # send_shortMessage()  # 发送告警短信到用户手机
    else:
        pass


# MQ-2烟雾传感器监控
def smokeMonitoring():
    if smoke.is_off():  # 监测高电平则表示MQ-2烟雾传感器检测到有害气体
        print("监测到有烟雾传感器报警...")
        led2.blink()  # 红灯警告
        mqttClient.publish(topics['topic4'], json.dumps(
            {"smoke": 1}), 0)  # 发布MQTT消息到阿里云物联网平台
        # send_shortMessage()  # 发送告警短信到用户手机
    else:
        pass


# 生成随机数
def randomNumber(str):
    length = len(str)
    num = random.randint(0, length - 1)
    return num


# 获取天气
def getWeatherData():
    # 实况天气
    # 101010100为城市代码
    url_now = "https://devapi.qweather.com/v7/weather/now?location=101010100&key=8bf5d16e26*****c82ac15030"
    # 生活指数
    url_lifestyle = "https://devapi.qweather.com/v7/indices/1d?type=8&location=101230101&key=8bf5d16e26******c82ac15030"
    response_now = requests.get(url=url_now)
    response_lifestyle = requests.get(url=url_lifestyle)
    self_now = response_now.json()
    self_lifestyle = response_lifestyle.json()
    data = '今天实时天气:' + self_now['now']['text'] + ',温度:' + \
        self_now['now']['temp'] + ',湿度:' + self_now['now']['humidity'] + ',风力:' + \
        self_now['now']['windScale'] + '级,' + \
        self_lifestyle['daily'][0]['text']
    print('data',data)
    return data

# dht11数据发布IOT
def getDHT11Data():
    humidity, temperature = Adafruit_DHT.read_retry(
        Adafruit_DHT.DHT11, 4)
    if humidity is not None and temperature is not None:
        global dht11
        dht11 = [temperature, humidity]
        print('dht11', dht11[0], dht11[1])
        # MQTT发布至阿里云物联网平台
        mqttClient.publish(topics['topic2'], json.dumps(
            {"temperature": temperature, "humidity": humidity}), 0)
        return temperature, humidity
    else:
        return 0



# 发送报警短信
# def send_shortMessage():
#     ssender = SmsSingleSender(
#         shortMessage_config['appid'], shortMessage_config['appkey'])
#     params = []
#     try:
#         result = ssender.send_with_param(86, shortMessage_config['phone_numbers'],
#                                          shortMessage_config['template_id'], params,
#                                          sign=shortMessage_config['sms_sign'], extend="", ext="")
#     except HTTPError as e:
#         print(e)
#     except Exception as e:
#         print(e)
#     print(result)


def on_mjpegstreamer_start():
    # 路径改成自己搭建的mjpg-streamer服务路径
    os.system("sh /home/pi/mjpg-streamer/mjpg-streamer-experimental/start.sh")


def callbacks():
    global detector
    print("成功唤醒小派!")
    snowboydecoder.play_audio_file()  # ding
    detector.terminate()  # close
    Speech(access_token)
    wake_up()


def on_connect(mqttClient, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    mqttClient.subscribe(topics['topic1'], 0)  # 接收指定服务器的消息


def on_disconnect(mqttClient, userdata, flags, rc):
    print("Disconnected.")


# 收到订阅消息
def on_message(mqttClient, userdata, msg):
    msg = str(msg.payload, encoding='utf8')
    # print(msg)
    setjson = json.loads(msg)
    print(setjson)
    ledChecked0 = setjson['ledList'][0]['ledChecked0']
    fanChecked0 = setjson['fanList'][0]['fanChecked0']
    led1.set_on() if ledChecked0 == 1 else led1.set_off()
    fan.set_off() if fanChecked0 == 1 else fan.set_on()


# mqtt连接
def on_mqtt_connect():
    mqttClient.on_connect = on_connect
    mqttClient.on_disconnect = on_disconnect
    mqttClient.on_message = on_message
    mqttClient.connect(
        host=aliyun_config['host'], port=aliyun_config['port'], keepalive=60)
    mqttClient.loop_forever()


def signal_handler(signal, frame):
    global interrupted
    interrupted = True


def interrupt_callback():
    global interrupted
    return interrupted


def wake_up():
    global detector
    # 唤醒词所在路径  根据需要修改
    model = '/home/pi/snowboy/resources/xiaopai.pmdl'
    signal.signal(signal.SIGINT, signal_handler)
    detector = snowboydecoder.HotwordDetector(model, sensitivity=0.6)
    print('我在听...请说唤醒词:小派...')
    # main loop
    detector.start(detected_callback=callbacks,
                   interrupt_check=interrupt_callback, sleep_time=0.01)
    detector.terminate()


def thread1():
    while 1:
        humanMonitoring()
        time.sleep(3)


def thread2():
    while 1:
        smokeMonitoring()
        time.sleep(3)


def thread3():
    while 1:
        getDHT11Data()
        time.sleep(3)


def thread4():
    on_mjpegstreamer_start()


def thread5():
    on_mqtt_connect()


if __name__ == '__main__':
    # os.close(sys.stderr.fileno()) 调试好后可开启该条指令 唤醒很有很多不影响的警告信息 调试过程注释因为报错会不打印
    led1 = Light(26)  # led1 BCM 26, BRAND 39 黄灯
    led2 = Light(12)  # led1 BCM 12, BRAND 34 红灯
    fan = Init(23)  # 风扇 BCM 23, VCC BRAND 4, GND BRAND 14
    # dht = Init(4)  # dht11 BCM 4,VCC BRAND 1 ,GND BRAND 9
    smoke = Init(18)  # 烟雾传感器 BCM 18, VCC BRAND 2 ,GND BRAND 6
    human = Init(22)  # 热释电红外传感器 BCM 22, VCC BRAND 17, GND BRAND 25
    access_token = getaccess_token()
    client = AipSpeech(
        baidu_config['APP_ID'], baidu_config['API_KEY'], baidu_config['SECRET_KEY'])
    mqttClient = iot.getAliyunIotMqttClient(aliyun_config['productKey'], aliyun_config['deviceName'],
                                            aliyun_config['deviceSecret'],
                                            secure_mode=3)
    _thread.start_new_thread(thread1, ())
    _thread.start_new_thread(thread2, ())
    _thread.start_new_thread(thread3, ())
    _thread.start_new_thread(thread4, ())
    _thread.start_new_thread(thread5, ())
    verify()
