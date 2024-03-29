#!/usr/bin/env python3

import json
import logging as log
from flask import Flask
from git import Repo, util
from webhook import Webhook
from os import environ as env, path
from urllib.parse import urlparse
from argparse import ArgumentParser
from subprocess import check_output, CalledProcessError

app = Flask(__name__)
webhook = Webhook(app, endpoint='/gh_webhook')

@app.route('/health')
def hello_world():
    return 'OK'


class ManagedRepo:

    def __init__(self, url, branch, dest_path):
        self.url = url
        self.branch = branch
        self.path = dest_path
        self._init()
        self._checkout()
        self.force_pull()

    def _init(self):
        self.repo = Repo.init(self.path)
        self.repo.description = self.name
        if 'origin' in self.repo.remotes:
            self.origin = self.repo.remotes['origin']
        else:
            self.origin = self.repo.create_remote('origin', self.url)
        log.debug('Fetching from: %s', self.origin.url)
        self.origin.fetch()
        self.remote_ref = self.origin.refs[self.branch]

    def _checkout(self):

        if self.repo.head.ref.name != self.branch:
            log.debug('Creating HEAD: %s', self.branch)
            head = self.repo.create_head(self.branch, self.remote_ref)
            self.repo.head.set_reference(head)

        if self.repo.head.ref.tracking_branch() != self.remote_ref:
            log.debug('Setting tracking branch: %s', self.remote_ref)
            self.repo.head.ref.set_tracking_branch(self.remote_ref)

        log.debug('Checking out: %s', self.branch)
        self.repo.head.ref.checkout()

    @property
    def name(self):
        if self.url.startswith('https://'):
            name = urlparse(self.url).path.strip('/')
        else:
            name = self.url.split(':').pop()
        if name.endswith('.git'):
            name = name[:-4]
        return name

    @property
    def commit(self):
        return self.repo.head.commit

    def fetch(self):
        return self.repo.remote().fetch()

    def reset(self):
        return self.repo.head.reset(commit=self.remote_ref, working_tree=True)

    def force_pull(self):
        log.debug('Resetting repo from: %s', self.commit)
        commit_before = self.commit
        self.fetch()
        self.reset()
        commit_after = self.commit
        log.debug('Reset repo to: %s', commit_after)
        return (commit_before, commit_after)



def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]

def run_command(command):
    log.info('Running command: %s', command)
    try:
        output = check_output(command.split())
    except CalledProcessError as err:
        log.error('Command failed, return code: %d' % err.returncode)
        log.error('Command stdout:\n%s', err.output)
    else:
        log.info('Command success:\n%s', output)

def define_push_hook(repo, post_action):
    @webhook.hook()
    def on_push(data):
        branch = remove_prefix(data['ref'], 'refs/heads/')
        name = data['repository']['full_name']

        if name != repo.name:
            log.error('Wrong repo: Event(%s) != Local(%s)', name, repo.name)
            return
        if branch != repo.branch:
            log.error('Wrong branch: Event(%s) != Local(%s)', branch, repo.branch)
            return

        new_commit = data['head_commit']['id']
        log.info('New commit available: %s', new_commit)

        before, after = repo.force_pull()

        if before == after:
            log.error('Failed to update repo, stuck on: %s', before)
        else:
            log.info('Updated repo to: %s', after)

        if post_action is not None:
            log.info('Running post action!')
            post_action()

def parse_args():
    parser = ArgumentParser(
        description='GitHub Webhook server to pull repos.',
        epilog='Example: ./gh_webhook.py -P 8080 -r "my-org/repo-a:master" /some/path'
    )
    parser.add_argument('path', help='Location where the repos should be synced.')
    parser.add_argument('-l', '--log-level', help='Logging level', default='info')
    parser.add_argument('-P', '--port', default=9090, help='Server listen port.')
    parser.add_argument('-H', '--host', default='localhost', help='Server listen host.')
    parser.add_argument('-p', '--post-command', help='Command to run after repo update.')
    parser.add_argument('-r', '--repo-url', help='Git repository URL.')
    parser.add_argument('-b', '--repo-branch', default='master',
                        help='Git repository branch.')
    parser.add_argument('-S', '--secret', default=env.get('WEBHOOK_SECRET'),
                        help='Webhook secret for authentication.')
    return parser.parse_args()


def main():
    args = parse_args()

    log.root.handlers=[]
    log.basicConfig(
        format='%(levelname)s - %(message)s',
        level=args.log_level.upper()
    )

    if args.secret:
        webhook.secret = args.secret

    # Initialize repository to manage
    repo = ManagedRepo(args.repo_url, args.repo_branch, args.path)

    post_command = None
    if args.post_command:
        post_command = lambda: run_command(args.post_command)

    # Define handler for webhook requests.
    define_push_hook(repo, post_command)

    # Start the server.
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
