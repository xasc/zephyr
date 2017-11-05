#!/usr/bin/env python3

import enum
import glob
import os
import re
import subprocess

from collections import Counter, namedtuple


class _Type(enum.Enum):
    FILE = '-'
    DIR = 'd'

_ZEPHYR_BASE = os.environ['ZEPHYR_BASE']
_BLACKLIST = ['.git', 'outdir', 'sanity-out']  # Directory names ignored during search

Selectors = namedtuple('Selectors', ['full_dir', 'single_file'])


def _find_orphaned_files(base_dir):
    with open(os.path.join(_ZEPHYR_BASE, 'CODEOWNERS'), 'r') as file:
        pattern = r'^(?!#)(.*?)\s+@'
        owned_files = [re.match(pattern, line).group(1)
                       for line in file.readlines()
                       if re.match(pattern, line)]

    def is_dir_owned(dir, selectors):
        if os.path.realpath(os.path.join(_ZEPHYR_BASE, dir)) \
                in selectors.full_dir:
            return True
        return False

    def is_file_owned(file, selectors):
        if os.path.realpath(os.path.join(_ZEPHYR_BASE, file)) \
                in selectors.single_file:
            return True
        return False

    def is_blacklisted(dir):
        if os.path.basename(dir) in _BLACKLIST:
            return True
        return False

    def classify_selectors(paths):
        full_dir = []
        single_file = []
        select_subdirs = re.compile(r'(.*?)(?:/\*$)')
        for path in paths:
            if path.count('*') == 0:
                if os.path.isfile(path):
                    single_file.append(path)
                else:
                    full_dir.append(os.path.realpath(path))
            elif path.count('*') < 2 and select_subdirs.search(path):
                # All childs of current dir are selected
                full_dir.append(os.path.realpath(
                    select_subdirs.search(path).group(1)))
            else:
                if select_subdirs.search(path):
                    # Can be reduced to dir with children
                    matches = [os.path.realpath(path) for path in
                               glob.glob(select_subdirs.search(path).group(1))]
                    full_dir.append(*matches)
                else:
                    matches = [os.path.realpath(match) for match in
                               glob.glob(path)]
                    for match in matches:
                        if os.path.isfile(match):
                            single_file.append(match)
                        else:
                            full_dir.append(match)
        return Selectors(full_dir, single_file)

    selectors = classify_selectors(owned_files)
    orphaned_items = []
    for root, dirs, files \
            in os.walk(os.path.realpath(_ZEPHYR_BASE), topdown=True):
        if is_blacklisted(root) or is_dir_owned(root, selectors):
            if is_blacklisted(root):
                print('{} is blacklisted.'.format(root))
            dirs[:] = []  # Do not recurse into subdirectories
        elif files:
            orphaned = [os.path.join(root, file) for file in files if
                        not is_file_owned(os.path.join(root, file), selectors)]
            if orphaned:
                if len(orphaned) == len(files):
                    orphaned_items.append((_Type.DIR, root))
                else:
                    orphaned_items += [(_Type.FILE, file) for file in orphaned]
    return orphaned_items


def _display_history(item):
    if item[0] == _Type.FILE:
        git_cmd = 'git log --format=short --follow'
    else:
        git_cmd = 'git log --format=short'
    p = subprocess.run(' '.join([git_cmd, item[1]]),
                       stdout=subprocess.PIPE, shell=True, check=True)
    commits = Counter(re.findall(r'Author:\s+(.*?\s+<.*?>)',
                                 p.stdout.decode('utf-8')))

    def print_top_contributors(commits):
        highest = commits.most_common(1)[0][1]

        width_highest = len(str(highest))
        width_bar = min(highest, 10)
        for idx, (author, count) in enumerate(commits.most_common(3)):
            if highest < 10:
                bar = '#' * count
            else:
                bar = '#' * int(round(count / highest, 1) * 100 // 10)
            print('{:>{width_highest}} | {:<{width_bar}} {}'
                  .format(count, bar, author,
                          width_highest=width_highest, width_bar=width_bar))

    name = item[1].replace(_ZEPHYR_BASE + os.sep, '')
    if commits:
        print('{} {}:'.format(item[0].value, name))
        print_top_contributors(commits)
    else:
        print('{} {} - not tracked.'.format(item[0].value, name))
    print()


def main():
    os.chdir(_ZEPHYR_BASE)
    for item in _find_orphaned_files(_ZEPHYR_BASE):
        _display_history(item)


if __name__ == '__main__':
    main()

