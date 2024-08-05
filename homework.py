import logging
import os
import requests
import sys
import time

from dotenv import load_dotenv
from http import HTTPStatus
from telebot import TeleBot
import telebot
from pprint import pprint

import exceptions


load_dotenv()

# PRACTICUM_TOKEN = 11
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN', None)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', None)
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', None)
# TELEGRAM_CHAT_ID = 11

# RECUIRED_CONSTANTS = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

FORMATTER = logging.Formatter(
    '%(asctime)s - [%(levelname)s] - %(filename)s: '
    '%(funcName)s: %(lineno)s - %(message)s'
)

# переписать в строчку или вообще через logging
def get_console_handler():
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(FORMATTER)
    return console_handler


def get_console_logger(logger_name):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(get_console_handler())
    logger.propagate = False
    return logger


logging.basicConfig( # описать нормально
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,
)
# logger = get_console_logger(__name__)


def check_tokens():
    """Проверяет доступность требуемых переменных окружения."""
    required_constants = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    for constant in required_constants:
        if constant is None:
            return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        # logger.error(f'Сбой при отправке сообщения. {error}')
        logging.error(f'Сбой при отправке сообщения. {error}')
    else:
        logging.debug(f'Успешная отправка сообщения: "{message}"')
        # logger.debug(f'Успешная отправка сообщения: "{message}"')


def get_api_answer(timestamp):
    """Делает запрос к API и в случе успеха возвращает ответ в формате JSON."""
    if not isinstance(timestamp, int):
        raise TypeError(f'Неожиданный тип входных данных: {type(timestamp)}')
    try:
        response = requests.get(ENDPOINT, headers=HEADERS,
                                params={'from_date': timestamp})
    except requests.RequestException as error:  # Это надо переписать по-человечески
        # logger.warning(error)
        logging.warning(error)
        return None
    if response.status_code != HTTPStatus.OK:
        raise exceptions.UnsuccessfulResponse()
    return response.json()


def check_response(response):
    """Проверяет ответ API и возвращает словарь, с ожидаемыми данными."""
    expected_keys = ['current_date', 'homeworks']
    data_for_expected_keys = dict()

    if not isinstance(response, dict):
        raise TypeError(f'Неожиданный тип входных данных: {type(response)}')
    
    for key in expected_keys:
        data_for_expected_keys[key] = response.get(key)
        if data_for_expected_keys[key] is None:
            raise KeyError(f'Ожидаемый ключ "{key}" отсутствует в ответе API.')
        if key == 'homeworks' and not isinstance(response.get(key), list):
            raise TypeError(f'Под ключом "{key}" данные не в виде списка.')
    return data_for_expected_keys



def parse_status(homework):
    """Докстринг"""
    expected_keys = ['homework_name', 'status']
    
    if not isinstance(homework, dict):
        raise TypeError(f'Неожиданный тип входных данных: {type(homework)}')
    for key in expected_keys:
        if homework.get(key) is None:
            raise KeyError(
                f'Ожидаемый ключ "{key}" отсутствует в данных о работе.'
            )
    status = homework.get('status')
    homework_name = homework.get('homework_name')
    if HOMEWORK_VERDICTS.get(status) is None:
        raise KeyError(
            f'Неожиданный статус работы "{status}", обнаруженный в ответе API.'
        )
    return (f'Изменился статус проверки работы "{homework_name}". '
            f'{HOMEWORK_VERDICTS[status]}')

     


def main():
    """Основная логика работы бота."""

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    
    last_message = None
    message = None  # это костыль для теста


    while True:
        if not check_tokens():
            logging.critical(
                'Бот остановлен. Обязательная переменная окружения '
                'не обнаружена.'
            )
            # logger.critical(
            #     'Бот остановлен. Обязательная переменная окружения '
            #     'не обнаружена.'
            # )
            break
        try:
            response = get_api_answer(timestamp)
            data = check_response(response)  # временное имя
            if not data['homeworks']:
                logging.debug('Статус работы не изменился.')
                # logger.debug('Статус работы не изменился.')
                continue
            timestamp = data['current_date']
            message = parse_status(data['homeworks'][0])
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            # logger.error(message)
        finally:
            if last_message != message:
                last_message = message
                send_message(bot, message)
            time.sleep(RETRY_PERIOD)
        # time.sleep(2)



if __name__ == '__main__':
    main()
