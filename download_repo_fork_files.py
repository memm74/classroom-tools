#!/usr/bin/env python3

# Author: Oliver Steele
# License: MIT

import argparse
import base64
import hashlib
import itertools
import os
import re
import sys

import yaml
from github import Github, GithubException

from utils import collect_repo_hashes, get_file_git_hash

DEFAULT_CONFIG_FILE = 'config/source_repos.yaml'
ORIGIN_DIRNAME = 'origin'

if 'ipykernel' in sys.modules:
    sys.argv = ['script', 'softdes']
    sys.argv = ['script', '--classroom', 'focs16fall/focs-2016fall-exam-1']

parser = argparse.ArgumentParser(description="Download all the forks of a GitHub repository.")
parser.add_argument("--classroom", action='store_true', help="Repo is a GitHub classroom")
parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="YAML configuration file")
parser.add_argument("--flatten", action='store_true', default=None, help="Flatten single-file repos")
parser.add_argument("--ignore-images", action='store_true', default=None)
parser.add_argument("--limit", type=int, metavar='N', help="download only the first N repos")
parser.add_argument("--match", metavar='SUBSTRING', help="download only repos that contains SUBSTRING")
parser.add_argument("repo", metavar='REPO_NAME', help="GitHub source repo, in format username/repo_name")
args = parser.parse_args(sys.argv[1:])

if args.flatten is None:
    args.flatten = args.classroom
if args.ignore_images is None:
    args.ignore_images = args.classroom

config = {}
if os.path.exists(args.config) or args.config != DEFAULT_CONFIG_FILE:
    with open(args.config) as f:
        config = yaml.load(f)

repo_config = config.get(args.repo, None) \
    or next((item for item in config.values() if item['source_repo'] == args.repo), {})

DROPPED_LOGINS = repo_config.get('dropped', [])
DOWNLOAD_PATH = repo_config.get('download_path', os.path.join('downloads', args.repo.replace('/', '-')))
INSTRUCTOR_LOGINS = repo_config.get('instructors', [])
SOURCE_REPO = repo_config.get('source_repo', args.repo)

GH_TOKEN = os.environ['GITHUB_API_TOKEN']
gh = Github(GH_TOKEN)

def download_contents(repo, dst_path):
    items = [item
             for item in repo.get_git_tree(repo.get_commits()[0].sha, recursive=True).tree
             if item.type == 'blob' and item.sha not in origin_file_hashes]

    if args.ignore_images:
        items = [item for item in items if not re.search(r'\.(gif|jpe?g|png)$', item.path, re.I)]

    flatten = args.flatten and len(items) == 1
    file_destinations = {item.path: dst_path + os.path.splitext(item.path)[1] if flatten else os.path.join(dst_path, item.path)
                         for item in items}

    updated_items = [item for item in items
                     if item.sha != get_file_git_hash(file_destinations[item.path], None)]

    if not items:
        print("%s: no files" % repo_owner_login(repo))
        return

    if not updated_items:
        print("%s: no new files" % repo_owner_login(repo))
        return

    print("%s:" % repo_owner_login(repo))
    for item in updated_items:
        print("  %s" % item.path)
        dst_name = file_destinations[item.path]
        os.makedirs(os.path.dirname(dst_name), exist_ok=True)
        blob = repo.get_git_blob(item.url.split('/')[-1])
        with open(dst_name, 'wb') as f:
            f.write(base64.b64decode(blob.content))

def repo_owner_login(repo):
    return repo.name[len(origin.name + '-'):] if args.classroom else repo.owner.login

origin = gh.get_repo(SOURCE_REPO)

if args.classroom:
    repos = [r for r in gh.get_user().get_repos() if r.owner == origin.owner and r.name.startswith(origin.name + '-')]
else:
    repos = origin.get_forks()

team = next((team for team in gh.get_organization(origin.organization.login).get_teams() if team.name == 'Instructors'), None)
instructor_logins = INSTRUCTOR_LOGINS + ([member.login for member in team.get_members()] if team else [])
repos = [repo for repo in repos if repo.owner not in instructors and repo_owner_login(repo) not in instructor_logins + DROPPED_LOGINS]
repos = sorted(repos, key=repo_owner_login)
if args.match: repos = [repo for repo in repos if args.match in repo_owner_login(repo)]
if args.limit: repos = repos[:args.limit]

origin_file_hashes = set(item.sha
                         for commit in origin.get_commits()
                         for item in origin.get_git_tree(commit.sha, recursive=True).tree)

for repo in repos:
    dirname = ORIGIN_DIRNAME if repo is origin else repo_owner_login(repo)
    download_contents(repo, os.path.join(DOWNLOAD_PATH, dirname))