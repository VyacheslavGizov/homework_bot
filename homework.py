import logging
import logging.handlers
import os
import requests
import sys
import time

from dotenv import load_dotenv
from http import HTTPStatus
from telebot import TeleBot
import telebot

import exceptions
#  поправить импорты

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
# PRACTICUM_TOKEN = 1
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
# TELEGRAM_TOKEN = 1
# TELEGRAM_CHAT_ID = 1
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
              '%(filename)s: %(funcName)s: %(lineno)s - %(message)s')


CHECK_TOKENS_ERROR = 'Не обнаружены переменные окружения: {not_found_vars}'
FAILED_SENDING = 'Сбой при отправке сообщения: "{message}".'
SUCCESSFUL_SENDING = 'Успешная отправка сообщения: "{message}".'
HTTP_REQUEST_ERROR = (
    'Ошибка при выполнении HTTP-запроса: {error}.\n'
    'Параметры запроса:\n'
    '    url: {url},\n'
    '    headers: {headers},\n'
    '    params: {params}.'
)


# переместить в main
# может сделать настройку логирования через словарь
logging.basicConfig(
    format=LOG_FORMAT,
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler(stream=sys.stdout),
        logging.handlers.RotatingFileHandler(
            filename=__file__ + '.log',
            maxBytes=10_000_000,
            backupCount=5)
    ],
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверит наличие требуемых переменных окружения."""
    required_variables = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    not_found_vars = []
    for var_name in required_variables.keys():
        if required_variables[var_name] is None:
            not_found_vars.append(var_name)
    if not_found_vars:
        message = CHECK_TOKENS_ERROR.format(not_found_vars=not_found_vars)
        logger.critical(message)
        raise ValueError(message)


def send_message(bot, message):
    """Отправит сообщение "message" в Телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SUCCESSFUL_SENDING.format(message=message))
        return True
    except Exception:
        logger.exception(FAILED_SENDING.format(message=message))


def get_api_answer(timestamp):
    """Сделает запрос к API Практикум.Домашка.
    В случе успеха вернет ответ API в виде словаря.
    """
    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        raise exceptions.HttpRequestError(
            HTTP_REQUEST_ERROR.format(
                error=error,
                headers=HEADERS,
                params={'from_date': timestamp}
            )
        )
    # нужно тестировать, дописывать, в данной ошибке пересылать параметры запроса, может параметры есть в error
    # отказы сервера
    if response.status_code != HTTPStatus.OK:
        raise exceptions.UnsuccessfulResponseError(
            f'HTTP-статус ответа API отличается от ОК: '
            f'Status-code {response.status_code}'
        )
    return response.json()


def check_response(response):
    """Проверит формат ответа API Практикум.Домашка.
    В случае соответствие ожидаемому формату вернет
    полученный ответ в виде словаря.
    """
    expected_keys = ['current_date', 'homeworks', ]
    keys_for_list = ['homeworks', ]

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
    """Проверит предоставленные данные о домашней работе.
    В случае соответствия данных ожидаемому формату
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
    """Основной цикл работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    # timestamp = int(time.time())
    timestamp = 0
    last_message = None
    # print(send_message(bot, 'Проверка связи'))
    print(HTTP_REQUEST_ERROR)

    while True:
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
