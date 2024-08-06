"""Модуль содержит функции Teлеграм-бота, поверяющего
статус домашней работы с использованием API Практикум.Домашка,
а также основной цикл работы бота
"""

import logging
import os
import requests
import sys
import time

from dotenv import load_dotenv
from http import HTTPStatus
from telebot import TeleBot

import exceptions


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

LOG_FORMAT = ('%(asctime)s - %(name)s - [%(levelname)s] - '
              '%(filename)s: %(lineno)s - %(message)s')

logging.basicConfig(
    format=LOG_FORMAT,
    level=logging.DEBUG,
    handlers=[logging.StreamHandler(stream=sys.stdout)],
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверит наличие требуемых переменных окружения."""
    required_constants = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    for constant in required_constants:
        if constant is None:
            return False
    return True


def send_message(bot, message):
    """Отправит сообщение "message" в Телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        logger.error(f'Сбой при отправке сообщения. {error}')
    else:
        logger.debug(f'Успешная отправка сообщения: "{message}"')


def get_api_answer(timestamp):
    """Сделает запрос к API Практикум.Домашка.
    В случе успеха вернет ответ API в виде словаря.
    """
    if not isinstance(timestamp, int):
        raise TypeError(f'Неожиданный тип входных данных функции '
                        f'get_api_answer(): {type(timestamp)}')
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except Exception as error:
        logger.error(f'Ошибка выполнения HTTP-запроса к API: {error}')
        return
    if response.status_code != HTTPStatus.OK:
        raise exceptions.UnsuccessfulResponse(
            f'HTTP-статус ответа API отличается от ОК: '
            f'Status-code {response.status_code}'
        )
    return response.json()


def check_response(response):
    """Проверит ответ API Практикум.Домашка в виде словаря
    на соответствие ожидаемому формату и в случае успеха вернет
    этот словарь.
    """
    expected_keys = ['current_date', 'homeworks',]
    keys_for_list = ['homeworks',]

    if not isinstance(response, dict):
        raise TypeError(f'Неожиданный тип входных данных функции '
                        f'check_response(): {type(response)}')
    for key in expected_keys:
        if key not in response:
            raise KeyError(f'Ожидаемый ключ "{key}" отсутствует в ответе API.')
        if key in keys_for_list and not isinstance(response[key], list):
            raise TypeError(f'Неожиданный тип данных {type(response[key])} '
                            f' полученных по ключу "{key}". Ожидается список.')
    return response


def parse_status(homework):
    """Проверит предоставленные данные о домашней работе
    и в случае соответствия данных ожидаемому формату
    вернет строку с иформацией о статусе данной работы.
    """
    expected_keys = ['homework_name', 'status']

    if not isinstance(homework, dict):
        raise TypeError(f'Неожиданный тип входных данных функции '
                        f'parse_status: {type(homework)}')
    for key in expected_keys:
        if key not in homework:
            raise KeyError(f'Ожидаемый ключ "{key}" отсутствует в данных '
                           f'о домашней работе.')
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f'Неожиданный статус домашней работы "{status}", '
                       f'обнаруженный в ответе API.')
    return (f'Изменился статус проверки работы "{homework["homework_name"]}". '
            f'{HOMEWORK_VERDICTS[status]}')


def main():
    """Создаст бота - объект класса Telebot
    и запустит основной цикл его работы."""

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    while True:
        if not check_tokens():
            logger.critical('Обязательная переменная окружения не обнаружена.'
                            'Бот остановлен. ')
            break
        try:
            response_data = check_response(get_api_answer(timestamp))
            if not response_data['homeworks']:
                logger.debug('Статус работы не изменился.')
                message = last_message
                continue
            timestamp = response_data['current_date']
            message = parse_status(response_data['homeworks'][0])
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
        finally:
            if last_message != message:
                last_message = message
                send_message(bot, message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
