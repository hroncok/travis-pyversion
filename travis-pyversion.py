import asyncio
import getpass
import sys

import aiohttp
import async_timeout
import click


PY_VERSION = f'{sys.version_info.major}.{sys.version_info.minor}'


async def fetch(session, url):
    with async_timeout.timeout(10):
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json(), response.headers


async def process_repo(repo):
    click.echo(repo['full_name'])


async def repos_page(session, url, page):
    repos, _ = await fetch(session, url.format(page))
    for repo in repos:
        asyncio.ensure_future(process_repo(repo))


async def all_repos(username):
    async with aiohttp.ClientSession() as session:
        url = f'https://api.github.com/users/{username}/repos?sort=pushed'
        repos, headers = await fetch(session, url)
        for repo in repos:
            await process_repo(repo)
        url, last_page = parse_last_page(headers['Link'])
        if last_page > 1:
            for p in range(2, last_page + 1):
                await asyncio.ensure_future(repos_page(session, url, p))


def parse_last_page(header):
    links = header.split(',')
    for link in links:
        link = link.strip()
        parts = link.split(';')
        if parts[1].strip() == 'rel="last"':
            url = parts[0].strip()[1:-1]
            for param in url.split('?')[1].split('&'):
                if param.startswith('page='):
                    last_page = int(param.split('=')[1])
                    break
            url = url.replace(f'page={last_page}', 'page={}')
            return url, last_page


@click.command()
@click.option('--username', prompt='GitHub username',
              help='Your GitHub username',
              default=getpass.getuser())
@click.option('--version', prompt='Python version',
              help='Python version to check',
              default=PY_VERSION)
@click.option('--token',
              help='GitHub token (optional, will fetch '
                   'anonymously if not provided, may hit rate limit)',
              prompt='GitHub token (leave empty for anonymous fetching)',
              hide_input=True,
              default='')
def main(username, version, token):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(all_repos(username))
    loop.close()


if __name__ == '__main__':
    main()
