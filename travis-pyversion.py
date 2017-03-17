import asyncio
import getpass
import sys

import aiohttp
import async_timeout
import click
import yaml


PY_VERSION = f'{sys.version_info.major}.{sys.version_info.minor}'


async def fetch_json_headers(session, url):
    with async_timeout.timeout(10):
        async with session.get(url, headers=session.headers) as response:
            response.raise_for_status()
            return await response.json(), response.headers


async def fetch_travis_yml(session, repo_slug):
    url = f'https://raw.githubusercontent.com/{repo_slug}/master/.travis.yml'
    with async_timeout.timeout(10):
        async with session.get(url) as response:
            if response.status == 404:
                return None
            response.raise_for_status()
            return yaml.load(await response.text())


def is_version_in_python(version, python):
    try:
        return version in python
    except TypeError:
        return version == str(python)


def versions_str(versions):
    if isinstance(versions, list):
        return ', '.join(sorted(str(version) for version in versions))
    else:
        return str(versions)


async def process_repo(session, repo, version, forks):
    if not forks and repo['fork']:
        return
    travis_yml = await fetch_travis_yml(session, repo['full_name'])
    if travis_yml is not None and 'python' in travis_yml:
        if is_version_in_python(version, travis_yml['python']):
            color = 'green'
            err = False
        else:
            color = 'red'
            err = True
        click.echo(click.style(repo['full_name'] + ': ', fg=color, bold=True) +
                   versions_str(travis_yml['python']), err=err)


async def repos_page(session, url, page, version, forks):
    futures = set()
    repos, _ = await fetch_json_headers(session, url.format(page))
    for repo in repos:
        futures.add(asyncio.ensure_future(process_repo(session, repo,
                                                       version, forks)))
    await asyncio.gather(*futures)


async def all_repos(username, version, token, repo_type, forks):
    futures = set()
    async with aiohttp.ClientSession() as session:
        if token:
            session.headers = {'Authorization': 'token ' + token}
        else:
            session.headers = dict()
        url = (f'https://api.github.com/users/{username}'
               f'/repos?sort=pushed&type={repo_type}&visibility=public')
        repos, headers = await fetch_json_headers(session, url)
        for repo in repos:
            futures.add(asyncio.ensure_future(process_repo(session, repo,
                                                           version, forks)))
        url, last_page = parse_last_page(headers['Link'])
        if last_page > 1:
            for p in range(2, last_page + 1):
                futures.add(asyncio.ensure_future(repos_page(session, url, p,
                                                             version, forks)))
        await asyncio.gather(*futures)


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
@click.option('--repo-type',
              type=click.Choice(['all', 'owner', 'member']),
              help='Repo types to check, default: all',
              default='all')
@click.option('--forks/--no-forks', default=False,
              help='Whether to check forks (default is not to)')
def main(username, version, token, repo_type, forks):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(all_repos(username, version, token,
                                      repo_type, forks))
    loop.close()


if __name__ == '__main__':
    main()
