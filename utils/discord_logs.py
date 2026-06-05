import traceback

from config.constants import ADMIN_LOG_CHANNEL_ID


async def push_admin_log(client, message):
    await safe_push_admin_log(client, message)


async def safe_push_admin_log(client, message):
    try:
        await _send_admin_log(client, message)
    except Exception as error:
        print(f'Failed to push admin log: {error}')


async def log_error(client, title, error=None, context=None):
    message_parts = [f'**{title}**']
    if context:
        message_parts.append(context)
    if error is not None:
        message_parts.append(f'```text\n{_format_error(error)}\n```')

    await safe_push_admin_log(client, '\n'.join(message_parts))


async def _send_admin_log(client, message):
    channel = client.get_channel(ADMIN_LOG_CHANNEL_ID)
    if channel is None:
        channel = await client.fetch_channel(ADMIN_LOG_CHANNEL_ID)
    for chunk in _chunks(message, 1900):
        await channel.send(chunk)


def _format_error(error):
    formatted = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    return formatted[-1500:]


def _chunks(message, size):
    if not message:
        return ['(empty log message)']
    return [message[index:index + size] for index in range(0, len(message), size)]
