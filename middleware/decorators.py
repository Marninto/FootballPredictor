from functools import wraps


def require_admin(settings):
    def decorator(command):
        @wraps(command)
        async def wrapper(ctx, *args, **kwargs):
            if ctx.author.id not in settings.admin_user_ids:
                await ctx.send('You do not have permission to use this command.')
                return

            return await command(ctx, *args, **kwargs)

        return wrapper

    return decorator
