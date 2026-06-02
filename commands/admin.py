from middleware.decorators import require_admin


def register_admin_commands(bot, settings):
    @bot.command(name='admin_check')
    @require_admin(settings)
    async def admin_check(ctx):
        await ctx.send('Admin access confirmed.')
