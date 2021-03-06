"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""

import re
import typing
from textwrap import shorten

import discord
from discord.ext import commands, menus
from utils.paginator import RoboPages


class SubredditPageSource(menus.ListPageSource):
    """ For discord.ext.menus to format Subreddit queries. """

    def __init__(self, data):
        self.data = data
        super().__init__(data, per_page=1)

    async def format_page(self, menu, page):
        """ Format each page entry. """
        return page


class SubredditPost:
    """ Let's try and create a generic object for a subreddit return... """

    def __init__(self, subreddit_dict: dict, *, video_link: str, image_link: str):
        """ Hrm. """
        self.url = f"https://reddit.com/{subreddit_dict['permalink']}"
        self.resp_url = subreddit_dict["url"]
        self.subreddit = subreddit_dict["subreddit_name_prefixed"]
        self.title = shorten(subreddit_dict["title"], width=200)
        self.upvotes = int(subreddit_dict["ups"])
        self.text = shorten(subreddit_dict.get("selftext", None), width=2000)
        self.nsfw = subreddit_dict.get("over_18", False)
        self.thumbnail = subreddit_dict.get("thumbnail", None)
        self.comment_count = subreddit_dict.get("num_comments", 0)
        self.author = f"/u/{subreddit_dict['author']}"
        self.video_link = video_link
        self.image_link = image_link


class Reddit(commands.Cog):
    """ For Reddit based queries. """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.headers = {"User-Agent": "Robo-Hz Discord bot"}

    def _gen_embeds(self, requester: str, iterable: list) -> typing.List[discord.Embed]:
        """ Generate many embeds from the top 10 posts on each subreddit. """
        embeds = []

        for item in iterable:
            embed = discord.Embed(
                title=item.title,
                description=item.text,
                colour=discord.Colour.red(),
                url=item.url,
            )

            embed.set_author(name=item.author)

            if item.image_link:
                embed.set_image(url=item.image_link)

            if item.video_link:
                embed.add_field(
                    name="Video", value=f"[Click me!]({item.video_link})", inline=False
                )

            embed.add_field(name="Upvotes", value=item.upvotes, inline=True)
            embed.add_field(name="Total comments", value=item.comment_count)
            fmt = f"Result {iterable.index(item)+1}/{len(iterable)}"
            embed.set_footer(
                text=f"{fmt} | {item.subreddit} | Requested by: {requester}"
            )

            embeds.append(embed)

        return embeds[:15]

    async def _perform_search(
        self, requester: str, channel: discord.TextChannel, subreddit: str, sort_by: str
    ):
        """ Performs the search for queries with aiohttp. Returns 10 items. """
        async with self.bot.session.get(
            f"https://reddit.com/r/{subreddit}/about.json", headers=self.headers
        ) as subr_top_resp:
            subr_deets = await subr_top_resp.json()

        if "data" not in subr_deets:
            raise commands.BadArgument("Subreddit not found.")
        if subr_deets["data"].get("over18", None) and not channel.is_nsfw():
            raise commands.NSFWChannelRequired(channel)

        params = {"t": "all" if sort_by == "top" else ""}

        async with self.bot.session.get(
            f"https://reddit.com/r/{subreddit}/{sort_by}.json",
            headers=self.headers,
            params=params,
        ) as subr_resp:
            subreddit_json = await subr_resp.json()

        subreddit_pages = []
        common_img_exts = (".jpg", ".jpeg", ".png", ".gif")

        idx = 0
        for post_data in subreddit_json["data"]["children"]:
            image_url = None
            video_url = None

            if idx == 20:
                break

            _short = post_data["data"]
            if _short.get("stickied", False) or (
                _short.get("over_18", False) and not channel.is_nsfw()
            ):
                idx += 1
                continue

            image_url = (
                _short["url"] if _short["url"].endswith(common_img_exts) else None
            )
            if "v.redd.it" in _short["url"]:
                image_url = _short["thumbnail"]
                video_teriary = _short.get("media", None)
                if video_teriary:
                    video_url = _short["url"]
                else:
                    continue

            subreddit_pages.append(
                SubredditPost(_short, image_link=image_url, video_link=video_url)
            )
            idx += 1

        return self._gen_embeds(requester, subreddit_pages[:30])

    @commands.command(name="reddit")
    @commands.cooldown(5, 300, commands.BucketType.user)
    async def _reddit(
        self, ctx: commands.Context, subreddit: str, sort_by: str = "hot"
    ):
        """ Main Reddit command, subcommands to be added. """
        sub_re = re.compile(r"(/?(r/)?(?P<subname>.*))")
        sub_search = sub_re.search(subreddit)
        if sub_search.group("subname"):
            subreddit = sub_search["subname"]
        embeds = await self._perform_search(
            str(ctx.author), ctx.channel, subreddit, sort_by
        )
        if not embeds:
            raise commands.BadArgument("Bad subreddit.", subreddit)
        pages = RoboPages(source=SubredditPageSource(embeds), delete_message_after=True)
        await pages.start(ctx)

    @_reddit.error
    async def reddit_error(self, ctx, error):
        """ Local Error handler for reddit command. """
        error = getattr(error, "original", error)
        if isinstance(error, commands.NSFWChannelRequired):
            return await ctx.send("This ain't an NSFW channel.")
        elif isinstance(error, commands.BadArgument):
            msg = (
                "There seems to be no Reddit posts to show, common cases are:\n"
                "- Not a real subreddit.\n"
            )
            return await ctx.send(msg)


def setup(bot):
    """ Cog entrypoint. """
    bot.add_cog(Reddit(bot))
