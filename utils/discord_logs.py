import traceback

from config.constants import ADMIN_LOG_CHANNEL_ID, PREDICTION_AWARD_CHANNEL_ID


async def push_admin_log(client, message):
    await safe_push_admin_log(client, message)


async def push_prediction_award_log(client, message):
    await _safe_send_channel_message(client, PREDICTION_AWARD_CHANNEL_ID, message)


async def safe_push_admin_log(client, message):
    await _safe_send_channel_message(client, ADMIN_LOG_CHANNEL_ID, message)


async def log_error(client, title, error=None, context=None):
    message_parts = [f'**{title}**']
    if context:
        message_parts.append(context)
    if error is not None:
        message_parts.append(f'```text\n{_format_error(error)}\n```')

    await safe_push_admin_log(client, '\n'.join(message_parts))


async def _send_admin_log(client, message):
    await _send_channel_message(client, ADMIN_LOG_CHANNEL_ID, message)


async def _safe_send_channel_message(client, channel_id, message):
    try:
        await _send_channel_message(client, channel_id, message)
    except Exception as error:
        print(f'Failed to push Discord channel message: {error}')


async def _send_channel_message(client, channel_id, message):
    channel = client.get_channel(channel_id)
    if channel is None:
        channel = await client.fetch_channel(channel_id)
    for chunk in _chunks(message, 1900):
        await channel.send(chunk)


def _format_error(error):
    formatted = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    return formatted[-1500:]


def _chunks(message, size):
    if not message:
        return ['(empty log message)']
    return [message[index:index + size] for index in range(0, len(message), size)]
