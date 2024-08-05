import logging
import os
import requests
import sys
import time

from dotenv import load_dotenv
from http import HTTPStatus
from telebot import TeleBot
import telebot

import exceptions


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN', None)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', None)
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', None)

# RECUIRED_CONSTANTS = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

timestamp = None
current_status = None
current_error = None

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


def check_tokens():
    """Докстринг"""
    required_constants = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]
    for constant in required_constants:
        if constant is None:
            return False
    return True
# def check_tokens(required_constants):
#     """Докстринг"""
#     for constant in required_constants:
#         if constant is None:
#             return False
#     return True


# def send_message(bot, message):
#     """Докстринг"""
#     if message:
#         bot.send_message(TELEGRAM_CHAT_ID, message)
#         return True
#     return False

def send_message(bot, message):
    """Докстринг"""
    if message:
        try:
            bot.send_message(TELEGRAM_CHAT_ID, message)
        except Exception:
            pass
        return True
    return False
# def send_message(bot, message):
#     """Докстринг"""
#     if message:
#         try:
#             bot.send_message(TELEGRAM_CHAT_ID, message)
#         except Exception as error:
#             raise exceptions.MessageError(f'Ошибка: {error}')
#         return True
#     return False


def get_api_answer(timestamp):
    """Докстринг"""
    try:
        response = requests.get(ENDPOINT, headers=HEADERS,
                                params={'from_date': timestamp})
    except requests.RequestException:
        raise exceptions.RequestFailedError()
    else:
        if response.status_code != HTTPStatus.OK:
            raise exceptions.UnsuccessfulResponse()
        return response.json()


def check_response(response):
    """Докстринг"""
    global timestamp
    try:
        homeworks = response['homeworks']
        timestamp = response['current_date']
    except KeyError as error:
        raise exceptions.KeyNotFound(
            f'Ожидаемый ключ {error} отсутствует в ответе API.'
        )
    else:
        if not isinstance(homeworks, list):
            raise exceptions.WrongTypeInAPIResponse(
                f'Неожиданный тип данных, полученных из ответа API по ключу '
                f'homeworks: {type(homeworks)}.'
            )
        if len(homeworks) == 1:
            return homeworks[0]
        # может добавить исключение о том, что получено более одной работы


def parse_status(homework):
    """Докстринг"""
    if homework:
        try:
            status = homework['status']
            homework_name = homework['homework_name']
        except KeyError as error:
            raise exceptions.KeyNotFound(
                f'Ожидаемый ключ {error} отсутствует данных  '
                f'о работе, полученных из ответа API.'
            )
        else:
            global current_status
            if current_status == status:
                return None
            current_status = status
            try:
                return (f'Изменился статус проверки работы "{homework_name}". '
                        f'{HOMEWORK_VERDICTS[status]}')
            except KeyError as error:
                raise exceptions.KeyNotFound(
                    f'Неожиданный статус работы, обнаруженный '
                    f'в ответе API: {error}'
                )


def main():
    """Основная логика работы бота."""

    global current_error

    logger = get_console_logger(__name__)
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        # if not check_tokens(RECUIRED_CONSTANTS):
        if not check_tokens():
            logger.critical(
                'Бот остановлен. Обязательная переменная окружения '
                'не обнаружена.'
            )
            break
        try:
            message = parse_status(check_response(get_api_answer(timestamp)))
            if not message:
                logger.debug('Статус работы не изменился.')
        except Exception as error:
            logger.error(error)
            if isinstance(error, type(current_error)):
                message = None
            else:
                current_error = error
                message = f'Сбой в работе программы: {error}'
        finally:
            try:
                if send_message(bot=bot, message=message):
                    logger.debug(f'Успешная отправка сообщения: "{message}"')
            except Exception as error:
                logger.error(f'Сбой при отправке сообщения. {error}')
            time.sleep(RETRY_PERIOD)

if __name__ == '__main__':
    main()
