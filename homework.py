from http import HTTPStatus
import logging
import logging.handlers
import os
import sys
import time

from dotenv import load_dotenv
from telebot import TeleBot
import requests

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
              '%(filename)s: %(funcName)s: %(lineno)s - %(message)s')

CHECK_TOKENS_ERROR = 'Не обнаружены переменные окружения: {not_found_vars}'
FAILED_SENDING = 'Сбой при отправке сообщения: "{message}".'
SUCCESSFUL_SENDING = 'Успешная отправка сообщения: "{message}".'
REQUEST_ERROR = (
    'Сбой сети! При выполнении GET-запроса с использованием '
    'requests.get() со следующими параметрами: {req_params} '
    'возникла ошибка: {error}.'
)
SERVER_ERROR = (
    'Отказ сервера! При выполнении GET-запроса с использованием '
    'requests.get() со следующими параметрами: {req_params} '
    'получен следующий ответ: {response}.'
)
UNSUCCESSFUL_RESPONSE = (
    'Неожиданный статус ответа! При выполнении GET-запроса с использованием '
    'requests.get() со следующими параметрами: {req_params} '
    'получен ответ с кодом возврата: {resp_status}. Ожидаемый код: 200.'
)
WRONG_INPUT_DATA = 'Неожиданный тип данных ответа сервера: {data_type}.'
HOMEWORKS_NOT_FOUND = 'Ожидаемый ключ {expected_key} отсутствует в ответе API.'
WRONG_DATA_TYPE = ('Неожиданный тип данных {data_type}, '
                   'полученных по ключу {key}.')
HOMEWORK_NAME_NOT_FOUND = ('Ожидаемый ключ "homework_name" отсутствует '
                           'в данных о домашней работе.')
STATUS_NOT_FOUND = ('Ожидаемый ключ "status" отсутствует '
                    'в данных о домашней работе.')
WRONG_HOMEWORK_STATUS = ('Неожиданный статус домашней работы "{status}", '
                         'обнаруженный в ответе API.')
HOMEWORK_STATUS_IS_CHANGED = ('Изменился статус проверки работы '
                              '"{homework_name}". {verdict}')
HOMEWORK_STATUS_NOT_CHANGED = 'Статус работы не изменился.'
ERROR_MESSAGE = 'Сбой в работе программы: {error}'


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
    except Exception:
        logger.exception(FAILED_SENDING.format(message=message))


def get_api_answer(timestamp):
    """Сделает запрос к API Практикум.Домашка.
    В случе успеха вернет ответ API в виде словаря.
    """
    req_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }
    try:
        response = requests.get(**req_params)
        resp_json = response.json()
        resp_status = response.status_code
    except requests.RequestException as error:
        raise exceptions.HttpRequestError(
            REQUEST_ERROR.format(req_params=req_params, error=error)
        )
    for item in ['code', 'error']:
        if item in resp_json:
            raise exceptions.ServerError(
                SERVER_ERROR.format(req_params=req_params, response=resp_json)
            )
    if resp_status != HTTPStatus.OK:
        raise exceptions.UnsuccessfulResponseError(
            UNSUCCESSFUL_RESPONSE.format(
                req_params=req_params,
                resp_status=resp_status
            )
        )
    return resp_json


def check_response(response):
    """Проверит формат ответа API Практикум.Домашка.
    В случае соответствие ожидаемому формату вернет
    полученный ответ в виде словаря.
    """
    expected_key = 'homeworks'
    if not isinstance(response, dict):
        raise TypeError(WRONG_INPUT_DATA.format(data_type=type(response)))
    if expected_key not in response:
        raise KeyError(HOMEWORKS_NOT_FOUND.format(expected_key=expected_key))
    if not isinstance(response[expected_key], list):
        raise TypeError(
            WRONG_DATA_TYPE.format(
                data_type=type(response[expected_key]),
                key=expected_key
            )
        )
    return response


def parse_status(homework):
    """Проверит предоставленные данные о домашней работе.
    В случае соответствия данных ожидаемому формату
    вернет строку с иформацией о статусе данной работы.
    """
    if 'homework_name' not in homework:
        raise KeyError(HOMEWORK_NAME_NOT_FOUND)
    if 'status' not in homework:
        raise KeyError(STATUS_NOT_FOUND)
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(WRONG_HOMEWORK_STATUS.format(status=status))
    return (
        HOMEWORK_STATUS_IS_CHANGED.format(
            homework_name=homework['homework_name'],
            verdict=HOMEWORK_VERDICTS[status]
        )
    )


def main():
    """Основной цикл работы бота."""
    logging.basicConfig(
        format=LOG_FORMAT,
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(stream=sys.stdout),
            logging.handlers.RotatingFileHandler(
                filename=__file__ + '.log',
                maxBytes=10_000_000,
                backupCount=5
            ),
        ],
    )

    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    while True:
        try:
            response_data = check_response(get_api_answer(timestamp))
            if len(response_data['homeworks']) == 0:
                logger.debug(HOMEWORK_STATUS_NOT_CHANGED)
                continue
            message = parse_status(response_data['homeworks'][0])
            if last_message != message:
                send_message(bot, message)
                timestamp = response_data.get('current_date', timestamp)
                last_message = message
        except Exception as error:
            message = ERROR_MESSAGE.format(error=error)
            logger.error(message, exc_info=True)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
