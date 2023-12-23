import re
import tqdm
import json
import time
import socks
import socket
import string
import random
import logging
import asyncio
import requests
import threading
import configparser
from tqdm import trange
from datetime import datetime
from pqdm.threads import pqdm
from pyppeteer import launcher
from tqdm.contrib.logging import logging_redirect_tqdm


# Импорт конфига
config = configparser.ConfigParser(default_section=None)
config.read('config.ini', 'UTF-8')
threadInstanceLock = threading.Lock()

# Инициализация переменных из конфига
TIMEOUT_OBJECT_WAITING = config.getint('GENERAL', 'TIMEOUT_OBJECT_WAITING') * 1000
WAITING_TIME_CHARACTERS_FROM = config.getfloat('GENERAL', 'WAITING_TIME_CHARACTERS_FROM')
WAITING_TIME_CHARACTERS_TO = config.getfloat('GENERAL', 'WAITING_TIME_CHARACTERS_TO')
WAITING_TIME_ACTION_FROM = config.getfloat('GENERAL', 'WAITING_TIME_ACTION_FROM')
WAITING_TIME_ACTION_TO = config.getfloat('GENERAL', 'WAITING_TIME_ACTION_TO')
COUNT_SITEWALKING = config.getint('GENERAL', 'COUNT_SITEWALKING')
THREADS = config.getint('GENERAL', 'THREADS')
ADS_API = config.get('GENERAL', 'ADS_API')
HEADLESS = config.getint('GENERAL', 'HEADLESS')
TIMEOUT_BROWSER = config.getint('GENERAL', 'TIMEOUT_BROWSER')
SITEWALKING_SITES = config.items('SITEWALKING')
PROXY_LIST = config.get('GENERAL','PROXY_LIST')
PREAPROVAL_TIMEOUT = config.getint('GENERAL', 'PREAPROVAL_TIMEOUT')
THREAD_LIFE = config.getint('GENERAL', 'THREAD_LIFE')
SCREEN_RESOLUTION = ['1366_768','1920_1080','1440_900','1536_864','1600_900']
FRAUD_LINKS = config.get('GENERAL', 'FRAUD_LINKS').split(',')
LOG = logging.getLogger(__name__)

if PROXY_LIST.startswith('http'): proxies = [proxy for proxy in requests.get(PROXY_LIST).text.splitlines() if proxy]
else: proxies = [proxy for proxy in open(PROXY_LIST,'r').read().splitlines() if proxy]

# Фильтры логера
class NoFutureFilter(logging.Filter):
    def filter(self, record):
        return not record.getMessage().startswith('[ERROR]: Future exception was never retrieved')
      
# Проверка прокси на работоспособность 
def checkSocks(sock):
    s = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.set_proxy(*sock)
        s.settimeout(5)
        host = "www.ya.ru"
        req = b"GET / HTTP/1.0\r\nHost: www.ya.ru\r\n\r\n"
        s.connect((host, 80))
        s.send(req)
        rsp = s.recv(4096).decode()
        s.close()
        if rsp.startswith("HTTP/1.1 301 Moved permanently"):
            return True
    except Exception as e:
        pass
    return False


# Случайное время ожидания между действиями
def randTimeSleep():
    time.sleep(random.uniform(WAITING_TIME_ACTION_FROM, WAITING_TIME_ACTION_TO))


# Асинхронный слип
async def async_sleep():
    wait_time = random.uniform(WAITING_TIME_ACTION_FROM, WAITING_TIME_ACTION_TO)
    await asyncio.sleep(wait_time)


# Задержка ввода символа
async def slow_type(element, text: str) -> None:
    for char in text:
        await element.press(char)
        await asyncio.sleep(random.uniform(WAITING_TIME_CHARACTERS_FROM,WAITING_TIME_CHARACTERS_TO)) 


# Создание профиля Ads
def create_ads_profile(api_key: str, proxy:str) -> str:
    url = api_key + '/api/v1/user/create'
    symbols = string.ascii_letters + string.digits
    random_name = ''.join(random.choice(symbols) for _ in range(6))
    proxy_user = ''
    proxy_password = ''
    if '@' in proxy:
        login_password_proxy, proxy = proxy.split('@')
        proxy_user, proxy_password = login_password_proxy.split(':')
    proxy_ip, proxy_port = proxy.split(':')
    payload = {
        "name": random_name,
        "group_id": "0",
        "repeat_config": ["0"],
        "ipchecker": "ip-api",
        "fingerprint_config": {
            "webrtc": "proxy",
            "screen_resolution": random.choice(SCREEN_RESOLUTION),
            "device_memory": random.choice(range(2,8,2))
        },
        "user_proxy_config": {
            "proxy_soft": "other",
            "proxy_type": "socks5",
            "proxy_host": proxy_ip,
            "proxy_port": proxy_port,
            "proxy_user": proxy_user,
            "proxy_password": proxy_password
        }
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.request("POST", url, headers=headers, json=payload)
    data = json.loads(response.text)
    ads_id = data['data']['id']
    start_url = api_key + '/api/v1/browser/start?user_id=' + ads_id + "&headless=" + str(HEADLESS)
    response = requests.request('GET', start_url)
    data = json.loads(response.text)
    ws = data['data']['ws']['puppeteer']
    return ads_id, ws


# Удаление профиля Ads
def delete_ads_profile(api_key:str ,ads_id: str) -> str:
    url = api_key + "/api/v1/user/delete"
    payload = {"user_ids": [ads_id]}
    headers = {'Content-Type': 'application/json'}
    response = requests.request("POST", url, headers=headers, json=payload)
    data = response.json()
    return data['msg']


# Функция отключения pyppeteer от браузера
async def disconnect(endpoint: str):
    async with asyncio.timeout(25):
        browser = await launcher.connect(browserWSEndpoint=endpoint)   
        await browser.close()
        await asyncio.sleep(5)


# Ходим по сайтам
async def siteWalking(endpoint: str) -> None:
    async with asyncio.timeout(THREAD_LIFE):
        # подключаемся к браузеру
        browser = await launcher.connect(browserWSEndpoint=endpoint, defaultViewport=None)
        page = await browser.pages()
        page = page[-1]
        # Выбираем случайный сайт из конфига
        sites = SITEWALKING_SITES.copy()
        random.shuffle(sites)
        for i in range(COUNT_SITEWALKING):
            site = sites[i]
            # Имимтируем скролинг по сайту
            try:
                # Переходим на него
                await page.goto(site[1], timeout=TIMEOUT_OBJECT_WAITING, waitUntil='domcontentloaded')
                await asyncio.sleep(random.uniform(WAITING_TIME_ACTION_FROM, WAITING_TIME_ACTION_TO)) 
                # Скролим
                for _ in range(random.randint(3,6)):
                    await page.keyboard.down('PageDown')  
                    await page.keyboard.up('PageDown')
                    await async_sleep()
                for _ in range(random.randint(1,4)):
                    await page.keyboard.down('PageUp')  
                    await page.keyboard.up('PageUp')
                    await async_sleep()
                for _ in range(random.randint(3,6)):
                    await page.keyboard.down('PageDown')  
                    await page.keyboard.up('PageDown')
                    await async_sleep()               
            except:
                browser = await launcher.connect(browserWSEndpoint=endpoint, defaultViewport=None)
                page = await browser.pages()
                page = page[-1]
        await browser.disconnect()


# Идём на discovercard
async def discoverCard(endpoint: str, line_str: str) -> None:
    async with asyncio.timeout(THREAD_LIFE):
        # Разбираем строку на элементы
        line = line_str.split(':')
        # подключаемся к браузеру
        browser = await launcher.connect(browserWSEndpoint=endpoint, defaultViewport=None)
        # Заходим на discovercard
        page = await browser.pages()
        page = page[-1]
        await page.goto('https://www.discovercard.com/', timeout=TIMEOUT_OBJECT_WAITING, waitUntil='domcontentloaded')
        await async_sleep()
        # Кликаем по кнопке Check Now
        await page.waitForSelector('.cmp-button', timeout=TIMEOUT_OBJECT_WAITING, visible=True)
        button = await page.querySelector('.cmp-button') 
        await button.click()
        # Ждём поле full-name и кликаем по нему
        await async_sleep()
        await page.waitForNavigation(timeout=TIMEOUT_OBJECT_WAITING, waitUntil='domcontentloaded')
        await page.waitForSelector('#full-name', timeout=TIMEOUT_OBJECT_WAITING, visible=True)
        await async_sleep()
        first_name = await page.querySelector('#full-name')
        await first_name.click()
        await slow_type(first_name, line[0])
        await async_sleep()
        # Заполняем last-name
        last_name = await page.querySelector('#last-name')
        await last_name.click()
        await slow_type(last_name, line[1])
        await async_sleep()
        # Заполняем address
        address_field = await page.querySelector('#home-address')
        await address_field.click()
        await async_sleep()
        address = re.sub(r'(.+?)\s*(APT\s|UNIT\s)?#*(\d+)?$', r'\1:\2\3', line[4]).split(':')
        street = await page.querySelector('#address')
        await street.click()
        await slow_type(street, address[0])
        await async_sleep()
        # Если есть APT то заполняем
        if address[1]:
            apt = await page.querySelector('#apt-num')
            await apt.click()
            await slow_type(apt, address[1])
            await async_sleep()
        # Заполняем city
        city = await page.querySelector('#city')
        await city.click()
        await slow_type(city, line[5])
        await async_sleep()
        # Выбираем state из списка
        state = await page.querySelector('#state')
        currentValue = await page.evaluate("(state) => state.value", state)
        if not currentValue:
            await state.click()
            await async_sleep()  
            await page.select('#state', line[6])
            await async_sleep()
        # Заполняем zip code
        zip_code = await page.querySelector('#zip-code')
        await zip_code.click()
        await slow_type(zip_code, line[7])
        await async_sleep()
        # Заполняем date
        date = line[3].split('/')
        data_field = await page.querySelector('#date-of-birth')
        await data_field.click()
        await slow_type(data_field, "%02d%02d%04d"%(int(date[0]),int(date[1]),int(date[2])))
        await async_sleep()
        # Заполняем social number
        social = await page.querySelector('#social-security-number')
        await social.click()
        await slow_type(social, line[2])
        await async_sleep()
        # Кликаем radio button
        student = await page.querySelector('#are-you-a-student-no')
        await student.click()
        await async_sleep()
        # Выбираем education из списка
        education = await page.querySelector('#highest-level-of-education')
        await education.click()
        await async_sleep()
        await page.select('#highest-level-of-education', 'BACHELORS_DEGREE')
        await async_sleep()
        # Заполняем payment
        payment = await page.querySelector('#monthly-house-or-rent-payment')
        await payment.click()
        await slow_type(payment, '0')
        await async_sleep()
        # Выбираем из списка housing-status
        housing = await page.querySelector('#housing-status')
        await housing.click()
        await async_sleep()
        await page.select('#housing-status', 'HOME')
        await async_sleep()
        # Заполняем gross
        gross_income = str(random.randint(150000,180000))
        line.append(f'${gross_income}')
        gross = await page.querySelector('#total-gross-income')
        await gross.click()
        await slow_type(gross, gross_income)
        await async_sleep()
        # Выбираем bank из списка
        bank = await page.querySelector('#bank-accounts-owned-select')
        await bank.click()
        await async_sleep()
        await page.select('#bank-accounts-owned-select', 'BOTH')
        await async_sleep()
        # Выбираем cards из списка
        card = await page.querySelector('#card-benefits')
        value = ['CASH_BACK', 'TRAVEL_REWARDS', 'BALANCE_TRANSFER', 'OTHER']
        await card.click()
        await async_sleep()
        await page.select('#card-benefits', random.choice(value))
        await async_sleep()
        # Подтверждаем agreement 
        agreement = await page.querySelector('#agree-to-paperless-disclosures-and-soft-pull')
        await agreement.click()
        await async_sleep()
        # Кликаем кнопку проверки
        check = await page.querySelector('#check-now-button')
        await check.click()
        await async_sleep()
        # Ожидаем загрузку
    await asyncio.sleep(PREAPROVAL_TIMEOUT)
    await page.waitForSelector('body')
    text = await page.Jeval('body', 'element => element.innerText')
    url = page.url
    good = False
    fraud = False
    if url == 'https://www.discovercard.com/application/preapproval/offers':
        if not 'Secured Credit Card' in text:
            good = True
    else:
        for fraud_link in FRAUD_LINKS:
            if url.startswith(fraud_link):
                fraud = True
    fileoutname = 'good.txt' if good else 'bad.txt'
    if fraud: fileoutname = 'fraud.txt'
    line = ':'.join(line)
    open(fileoutname,'a').write(line+'\n')
    rand_text = ''.join(random.choice(string.ascii_letters+string.digits) for i in range(10))
    timestamp = datetime.now().strftime("%d.%m.%Y.%H.%M")
    rand_text = f'{timestamp}_{rand_text}.txt'
    open(f'./logs/{rand_text}','w').write(f'##LINE: {line}\n##URL: {url}\n##TEXT:\n{text}')
    data = open('data_input.txt','r').read()
    data = data.replace(line_str+'\n','')
    open('data_input.txt','w').write(data)


# Основная функция
def mainTask(line_str: str) -> None:
    try:
        line_arr = line_str.split(':')
        while True:
            try:
                proxy = proxies.pop(0)
                proxy_str = proxy
                proxy_user = ''
                proxy_password = ''
                if '@' in proxy:
                    login_password_proxy, proxy = proxy.split('@')
                    proxy_user, proxy_password = login_password_proxy.split(':')
                proxy_ip, proxy_port = proxy.split(':')
                if checkSocks((socks.SOCKS5, proxy_ip, int(proxy_port), True, proxy_user, proxy_password)): 
                    break
                else:
                    tqdm.tqdm.write(f"[PROXY]: {proxy} is BAD, skip...")
            except:
                tqdm.tqdm.write(f"[ERROR]: No worked proxy!")
                break
        if len(line_arr) == 8:
            for _ in range(1, 4):
                threadInstanceLock.acquire()
                ads_id = None
                try:
                    ads_id, ws = create_ads_profile(ADS_API, proxy_str)
                except Exception as e:
                    tqdm.tqdm.write(f"[ERROR]: create_ads_profile: {repr(e)}")
                threadInstanceLock.release()
                if ads_id:
                    time.sleep(TIMEOUT_BROWSER)
                    break
                else: time.sleep(2)
            try:
                asyncio.run(siteWalking(ws))
            except Exception as e:
                tqdm.tqdm.write(f"[ERROR]: siteWalking: {repr(e)}")
            for _ in range(1, 4):
                try:
                    asyncio.run(discoverCard(ws, line_str))
                    break
                except Exception as e:
                    tqdm.tqdm.write(f"[ERROR]: discoverCard: {repr(e)}")
            for _ in range(1, 4):
                threadInstanceLock.acquire()
                deleted = 'failed'
                try:
                    asyncio.run(disconnect(ws))
                    deleted = delete_ads_profile(ADS_API, ads_id)
                except Exception as e:
                    tqdm.tqdm.write(f"[ERROR]: delete_ads_profile: {repr(e)}")
                threadInstanceLock.release()
                if deleted == 'Success':
                    time.sleep(2)
                    break 
        else:
            tqdm.tqdm.write(f'[ERROR] line: {line_str}')
            open('error_input.txt','a').write(line_str+'\n')
            data = open('data_input.txt','r').read()
            data = data.replace(line_str+'\n','')
            open('data_input.txt','w').write(data)
        proxies.append(proxy)
    except Exception as e: tqdm.tqdm.write(f"[ERROR GLOBAL]: {repr(e)}")

 
if __name__ == '__main__':
    input_data = [line for line in open('data_input.txt','r').read().splitlines() if line]
    LOG.addFilter(NoFutureFilter())
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s]: %(message)s') 
    with logging_redirect_tqdm():
        for i in trange(9):
            if i == 4:
                LOG.info("Console logging redirected to TQDM")
        pqdm(input_data, mainTask, n_jobs=THREADS) 