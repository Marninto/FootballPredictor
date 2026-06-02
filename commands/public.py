def register_public_commands(bot):
    @bot.command(name='ping')
    async def ping(ctx):
        await ctx.send('Pong')

