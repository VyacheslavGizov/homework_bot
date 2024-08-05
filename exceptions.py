class CustomError(Exception):
    message = 'CustomError has been raised'

    def __init__(self, *args):
        if args:
            self.message = args[0]

    def __str__(self):
        return f'{self.message}'


# class EnviromentVariableIsMissing(CustomError):
#     message = 'Обязательная переменная окружения не обнаружена.'


class UnsuccessfulResponse(CustomError):
    message = ('HTTP-статус ответа API отличается от ОК. '
               'Запрос не обработан.')


class RequestFailedError(CustomError):
    message = 'Возникла ошибка при выполнении HTTP-запроса.'


class KeyNotFound(CustomError):
    message = 'Ожидаемый ключ отсутствует.'


class WrongTypeInAPIResponse(TypeError):
    pass


class MessageError(CustomError):
    message = 'Сбой при отправке сообщения.'
