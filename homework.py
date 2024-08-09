from http import HTTPStatus
import logging
import logging.handlers
import os
import sys
import time

from dotenv import load_dotenv
from telebot import TeleBot
import requests

from exceptions import UnsuccessfulResponseError, ServerError


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

REQUIRED_CONSTANTS_NAMES = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN',
                            'TELEGRAM_CHAT_ID']

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
FAILED_SENDING = ('При отправке сообщения "{message}" возникла следующая '
                  'ошибка: {error}.')
SUCCESSFUL_SENDING = 'Успешная отправка сообщения: "{message}".'
REQUEST_ERROR = (
    'Сбой сети! При выполнении GET-запроса с использованием '
    'requests.get() со следующими параметрами: {request_params} '
    'возникла ошибка: {error}.'
)
SERVER_ERROR = (
    'Отказ сервера при выполнении GET-запроса с использованием '
    'requests.get() со следующими параметрами: {request_params}. '
    'Данные об ошибке: {error_info}.'
)
UNSUCCESSFUL_RESPONSE = (
    'Неожиданный статус ответа! При выполнении GET-запроса с использованием '
    'requests.get() со следующими параметрами: {request_params} '
    'получен ответ с кодом возврата: {response_status}. Ожидаемый код: 200.'
)
WRONG_INPUT_DATA = 'Неожиданный тип данных ответа сервера: {data_type}.'
KEY_NOT_FOUND_IN_RESPONSE = ('Ожидаемый ключ {key} отсутствует в'
                             ' ответе API.')
WRONG_DATA_TYPE = ('Неожиданный тип данных {data_type}, '
                   'полученных по ключу {key}.')
KEY_NOT_FOUND_IN_HOMEWORK = ('Ожидаемый ключ {key} отсутствует '
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
    not_found_vars = [name for name in REQUIRED_CONSTANTS_NAMES
                      if globals().get(name) is None]
    if not_found_vars:
        message = CHECK_TOKENS_ERROR.format(not_found_vars=not_found_vars)
        logger.critical(message)
        raise ValueError(message)


def send_message(bot, message):
    """Отправит сообщение "message" в Телеграм. В случае успеха вернет True."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(SUCCESSFUL_SENDING.format(message=message))
        return True
    except Exception as error:
        logger.exception(FAILED_SENDING.format(message=message, error=error))


def get_api_answer(timestamp):
    """Сделает запрос к API Практикум.Домашка.
    В случе успеха вернет ответ API в виде словаря.
    """
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }
    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            REQUEST_ERROR.format(request_params=request_params, error=error)
        )
    response_json = response.json()
    error_info = {key: response_json[key] for key in ['code', 'error']
                  if key in response_json}
    if error_info:
        raise ServerError(SERVER_ERROR.format(
            request_params=request_params,
            error_info=error_info
        ))
    response_status = response.status_code
    if response_status != HTTPStatus.OK:
        raise UnsuccessfulResponseError(UNSUCCESSFUL_RESPONSE.format(
            request_params=request_params,
            response_status=response_status
        ))
    return response_json


def check_response(response):
    """Проверит формат ответа API Практикум.Домашка.
    В случае соответствие ожидаемому формату вернет
    полученный ответ в виде словаря.
    """
    if not isinstance(response, dict):
        raise TypeError(WRONG_INPUT_DATA.format(data_type=type(response)))
    if 'homeworks' not in response:
        raise KeyError(
            KEY_NOT_FOUND_IN_RESPONSE.format(key='homeworks')
        )
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(WRONG_DATA_TYPE.format(
                data_type=type(homeworks),
                key='homeworks'
            ))
    return response


def parse_status(homework):
    """Проверит предоставленные данные о домашней работе.
    В случае соответствия данных ожидаемому формату
    вернет строку с иформацией о статусе данной работы.
    """
    if 'homework_name' not in homework:
        raise KeyError(KEY_NOT_FOUND_IN_HOMEWORK.format(key='homework_name'))
    if 'status' not in homework:
        raise KeyError(KEY_NOT_FOUND_IN_HOMEWORK.format(key='status'))
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(WRONG_HOMEWORK_STATUS.format(status=status))
    return HOMEWORK_STATUS_IS_CHANGED.format(
        homework_name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS[status]
        )


def main():
    """Основной цикл работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = None

    while True:
        try:
            response_data = check_response(get_api_answer(timestamp))
            homeworks = response_data['homeworks']
            if not homeworks:
                logger.debug(HOMEWORK_STATUS_NOT_CHANGED)
                continue
            message = parse_status(homeworks[0])
            if last_message != message:
                if send_message(bot, message):
                    timestamp = response_data.get('current_date', timestamp)
                    last_message = message
        except Exception as error:
            message = ERROR_MESSAGE.format(error=error)
            logger.error(message, exc_info=True)
            if last_message != message:
                if send_message(bot, message):
                    last_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
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
    main()
