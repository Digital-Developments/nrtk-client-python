#!/usr/bin/env python3
# coding: utf-8

"""Sync NRTK instance content with Newsroom Toolkit API

Stores articles as files in WWW_DIR. Landing page is stored as `index` file.
Error page content stored as error.html in WWW_DIR.

Each update creates new Snapshot based on `checksum` field of the response.
Expired content is being moved into a Snapshot directory inside BIN_DIR

To run the script set NRTK_API_URL and NRTK_API_TOKEN environment variables.

You can also set two optional envs:
- LOGLEVEL (str|int) to set needed Logging Level.
- INFINITY (str|int) in seconds to enable Infinity mode – the script will repeat sync with an interval of INFINITY.

Console Usage: main.py -l LOGLEVEL -i INFINITY

© 2025 LLC Digital Developments
www.nrtk.app
"""


__all__ = []
__version__ = '0.1.3'
__author__ = 'Mikhail Ageev'


import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import time
import urllib.request
import urllib.error


APP_DIR = '.nrtk'               # App directory to store Meta and content snapshots
WWW_DIR = 'www/'                # Directory to store content files
BIN_DIR = 'bin/'                # Snapshots (Bin) directory name
META_FILE_NAME = 'meta.json'    # Instance Meta information
LOG_FILE_NAME = 'sync.log'      # Log file name
MIN_SYNC_CYCLE = 60             # Minimal sync cycle pause in Infinity mode

BASE_PATH = os.path.dirname(__file__)
APP_PATH = os.path.join(BASE_PATH, APP_DIR)


def check_dir(dir_path=None):
    """Checks if the directory exists otherwise creates it

    :param dir_path: Dir absolute path
    :type dir_path: str
    """

    if dir_path:
        if not os.path.isdir(dir_path):
            try:
                os.mkdir(dir_path)
                return True
            except OSError as exc:
                logger.error(f"Unable to create app dirs at {dir_path}: {exc}")
                exit()
        else:
            logger.debug(f"Directory exists {dir_path}")
            return True

    return False


class NRTKSync(object):

    bin_path = None
    www_path = None
    meta_filepath = None
    meta_file_content = None    # Offline instance Meta
    meta_object = None          # Instance new Meta data

    story_dictonary = {}

    def __init__(self):

        logger.info("Starting Update")

        if not os.getenv('NRTK_API_URL', None) or not os.getenv('NRTK_API_TOKEN', None):
            logger.error("Unable to get API URL & Token")
            exit()

        else:
            self.api_url = os.getenv('NRTK_API_URL')
            self.api_token = os.getenv('NRTK_API_TOKEN')

        self.bin_root_path = os.path.join(APP_PATH, BIN_DIR)
        self.www_path = os.path.join(BASE_PATH, WWW_DIR)

        check_dir(self.bin_root_path)
        check_dir(self.www_path)

        self.meta_filepath = os.path.join(APP_PATH, META_FILE_NAME)

    def read_meta(self) -> dict:
        """Reads local Meta file if exists."""

        if os.path.isfile(self.meta_filepath):
            with open(self.meta_filepath, "r") as meta_file:
                try:
                    return json.load(meta_file)
                except OSError as exc:
                    logger.warning(f"Unable to read local Meta file at {self.meta_filepath}: {exc}")
                    return None
        else:
            logger.warning(f"Meta file is not found at {self.meta_filepath}")
            return None

    def save_meta(self):

        logger.info("Updating local Meta file")

        if self.meta_object:

            if self.bin_path and os.path.isfile(self.meta_filepath):
                meta_bin_path = os.path.join(self.bin_path, META_FILE_NAME)
                logger.warning(f"Moving old Meta into Bin > {meta_bin_path}")
                os.rename(self.meta_filepath, meta_bin_path)

            with open(self.meta_filepath, "w") as meta_file:
                try:
                    json.dump(self.meta_object, meta_file)
                    return True

                except ValueError:
                    logger.error("Meta config bad format")
                    logger.error(self.meta_object)
                    return False

        logger.warning('Meta config is empty')
        return False

    def create_sitemap_item(self, url=None, updated_at=None, priority=0.8):
        """Create sitemap page item.

        :param url: URL for the page.
        :type url: str
        :param updated_at: Latest update date and time.
        :type updated_at: str
        :param priority: Priority.
        :priority: float
        """

        return f'<url><loc>{url}</loc><lastmod>{updated_at[0:19]}+00:00</lastmod><priority>{priority}</priority></url>'

    def build_sitemap(self, sitemap_items=""):
        """Generates and saves sitemap.xml content for the snapshot

        :param sitemap_items: Concatenated string of Sitemap XML-formated items for each story in the snapshot
        :type sitemap_items: str
        """

        logger.info("Generating Sitemap")

        sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" 
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
            xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9 
            http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">
            <!-- Created by Newsroom Toolkit www.newsroomtoolkit.com -->
                {sitemap_items}
            </urlset>"""

        with open(f"{self.www_path}/sitemap.xml", "w") as sitemap_file:
            sitemap_file.write(sitemap_content)

    def save_error_page(self):

        if self.remote_data and 'error_page' in self.remote_data:

            try:
                logger.info("Creating Error page")
                with open(f"{self.www_path}/error.html", "w") as error_page_file:
                    error_page_file.write(self.remote_data['error_page'])
                return True

            except OSError as exc:
                logger.warning(f"Unable to save Error page content: {exc}")
                return False

        logger.warning("No content for Error page")
        return False

    def fetch_content(self):

        req = urllib.request.Request(self.api_url)
        req.add_header("Authorization", f"Token {self.api_token}")

        try:
            response = urllib.request.urlopen(req, timeout=20)

        except urllib.error.HTTPError as e:
            logger.error(f"HTTP Error {e.code} at {self.api_url}")
            return None

        except urllib.error.URLError as e:
            logger.error(f"Failed to fetch {self.api_url}: {e.reason}")
            return None

        else:
            return response

    def validate_api_response(self, response) -> bool:
        """Validate API response.
        Checks required data related to theme and stories (if any).

        :param response: urllib.response instance
        :type response: object
        """

        theme_required_fields = ('homepage_url', 'stories', 'error_page', 'entity', 'title',)
        story_required_fields = ('canonical_url', 'content', 'anchor', 'updated_at', 'title',
                                 'is_landing', 'hash', 'uid', 'credits',)

        if response and response.code == 200:

            try:
                self.remote_data = json.load(response)
                response_dump = json.dumps(self.remote_data, sort_keys=True)

                if self.remote_data:

                    for theme_field in theme_required_fields:
                        if theme_field not in self.remote_data:
                            logger.error(f"Invalid Response: unable to find `{theme_field}` in {response_dump[0:128]}...")
                            return False

                    if len(self.remote_data['stories']) > 0:
                        for story in self.remote_data['stories']:
                            for story_field in story_required_fields:
                                if story_field not in story:
                                    story_dump = json.dumps(story)[0:128]
                                    logger.error(f"Invalid Story: unable to find `{story_field}` in {story_dump}...")
                                    return False

                            self.story_dictonary[story['anchor']] = story
                    else:
                        logger.warning("No Stories recieved. Cleaning instance content")

                self.meta_object = {
                    "checksum": hashlib.sha256(response_dump.encode("utf-8")).hexdigest(),
                    "title": self.remote_data['title'],
                    "entity": self.remote_data['entity'],
                    "homepage_url": self.remote_data['homepage_url'],
                    "updated_at": str(dt.datetime.now(dt.timezone.utc)),
                }

                logger.debug("Valid API response")
                return True

            except json.JSONDecodeError:
                logger.error("Bad API Response - JSON expected")
                return False

        else:

            logger.error(f"Bad API response code: {response.code}")
            return False

    def clean_local_storage(self):
        """Runs through files in www dir and checks it against meta config and API response.
        Unknown files are being deleted.
        Removed stories (included into meta while not present in API) - are moved Bin 
        Updated stories (hashes do not match in meta and API) - are move to Bin
        """

        logger.info("Cleaning local storage")

        for file in os.listdir(self.www_path):

            file_path = os.path.join(self.www_path, file)

            if self.meta_file_content and 'stories' in self.meta_file_content and \
                    self.meta_file_content['stories'] and file in self.meta_file_content['stories']:

                if self.bin_path:

                    file_bin_path = os.path.join(self.bin_path, f"{file}")

                    if file in self.story_dictonary:

                        if self.story_dictonary[file]['hash'] != self.meta_file_content['stories'][file]['hash']:
                            logger.warning(f"Updating page {file}. Moving old version into Bin > {file_bin_path}")
                            os.rename(file_path, file_bin_path)

                    else:

                        logger.warning(f"Page {file} was removed. Moving file into Bin > {file_bin_path}")
                        os.rename(file_path, file_bin_path)

            else:
                logger.warning(f"Removing file {file_path}")
                os.remove(file_path)

    def sync_stories(self):
        """Sync local content with remote data.
        Creates local files in WWW_DIR named with the `anchor` field value of the story.
        Updates instance Meta data.
        Generates content for sitemap.xml.
        """

        self.clean_local_storage()

        self.meta_object['stories'] = {}

        sitemap_items = ''

        for story in self.remote_data['stories']:

            logger.info(f"Saving story: {story['anchor']}")
            with open(f"{self.www_path}/{story['anchor']}", "w") as story_file:
                story_file.write(story['content'])

            self.meta_object['stories'][story['anchor']] = {
                'anchor': story['anchor'],
                'hash': story['hash'],
                'canonical_url': story['canonical_url'],
                'updated_at': story['updated_at'],
            }

            sitemap_items += self.create_sitemap_item(url=story['canonical_url'],
                                                      updated_at=story['updated_at'],
                                                      priority=1 if 'index' == story['anchor'] else 0.8)

        self.build_sitemap(sitemap_items)

    def sync(self) -> bool:
        """Sync website remote content."""

        logger.debug("Content Sync")

        api_response = self.fetch_content()

        if api_response and self.validate_api_response(api_response):

            if not self.meta_file_content or 'checksum' not in self.meta_file_content or \
                    self.meta_file_content['checksum'] != self.meta_object['checksum']:
                logging.debug(f"Content update detected [{self.meta_object['checksum']}]. Sync stories")

                if self.meta_file_content and 'checksum' in self.meta_file_content:
                    logger.info(f"Creating Snapshot {self.meta_file_content['checksum']}")
                    self.bin_path = os.path.join(self.bin_root_path, self.meta_file_content['checksum'])
                    check_dir(self.bin_path)

                self.sync_stories()
                self.save_error_page()
                self.save_meta()

            else:
                logging.debug("Content is up to date")

            logging.info("Update Complete")
            return False

        logging.warning("Update Unsuccessful")
        return False


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Sync instance content with Newsroom Toolkit API",
        epilog="Learn more at nrtk.app")

    parser.add_argument("-l", "--loglevel")
    parser.add_argument("-i", "--infinity", default=0, type=int)

    args = parser.parse_args()

    loglevel = (os.getenv('LOGLEVEL', None) or (args.loglevel.upper() if args and args.loglevel else "DEBUG"))
    infinity_timer = int(os.getenv('INFINITY', None) or (args.infinity if args and args.infinity > 0 else 0))

    logger = logging.getLogger(__name__)

    check_dir(APP_PATH)

    log_path = os.path.join(APP_PATH, LOG_FILE_NAME)
    try:
        log_path = log_path if os.access(log_path, os.W_OK) else None
    except OSError:
        log_path = None

    logging.basicConfig(filename=log_path,
                        encoding="utf-8",
                        format='%(asctime)s %(message)s',
                        level=getattr(logging, loglevel, 10))

    sync = NRTKSync()

    if infinity_timer and infinity_timer >= MIN_SYNC_CYCLE:  # Check Infinity Mode ignoring short cycles

        logger.info(f"Infinity Mode ({infinity_timer} seconds)")

        while True:
            sync.meta_file_content = sync.read_meta()
            sync.sync()
            time.sleep(infinity_timer)

    else:
        sync.meta_file_content = sync.read_meta()
        sync.sync()
