import io
import os
import subprocess
from typing import Any, List, Tuple

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload

from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory

from src import ColorText
from src.AutoCompleter import AutoCompleter

import pickle
import os.path

from src.ReferenceVar import ReferenceVar
import src.QueryConstructor as _

SCOPES = ['https://www.googleapis.com/auth/drive']


def main(creds):
    """
        Performs the Google Drive CLI file system navigation.
    """
    page_token = None
    folder_stack: ReferenceVar[List[Tuple[str, str]]] = ReferenceVar([('root', 'root')])
    query: ReferenceVar[str] = ReferenceVar()
    online: ReferenceVar[bool] = ReferenceVar(True)
    service = build('drive', 'v3', credentials=creds)

    results: ReferenceVar[List[Any]] = ReferenceVar([])
    results.value = service.files().list(q=_.root_content() if query.value is None else query.value,
                                         spaces='drive',
                                         fields='nextPageToken, files(*)',
                                         pageToken=page_token).execute()

    def remove_login_token():
        if os.path.exists('token.pickle'):
            os.remove('token.pickle')
        online.value = False

    def go_into_folder(drive_items, name: str):
        if name == ".." and len(folder_stack) > 1:
            folder_stack.value.pop(0)
            query.value = _.list_all_in_folder(folder_stack.value[0][1])
            results.value = service.files().list(q=_.root_content() if query.value is None else query.value,
                                                 spaces='drive',
                                                 fields='nextPageToken, files(*)',
                                                 pageToken=page_token).execute()
            return
        wanted_items = list(filter(lambda i: i['name'] == name, drive_items))
        if len(wanted_items) == 0 or wanted_items[0]['mimeType'] != "application/vnd.google-apps.folder":
            print("Folder does not exist")
        else:
            item = wanted_items[0]
            folder_stack.value.insert(0, (item['name'], item['id']))
            query.value = _.list_all_in_folder(wanted_items[0]['id'])
            results.value = service.files().list(q=_.root_content() if query.value is None else query.value,
                                                 spaces='drive',
                                                 fields='nextPageToken, files(*)',
                                                 pageToken=page_token).execute()

    def print_items(drive_items):
        for item in drive_items:
            # , item['id'], item['mimeType']
            if item['mimeType'] == "application/vnd.google-apps.folder":
                print(ColorText.bcolors.OKBLUE, end='')
            print(item['name'])
            if item['mimeType'] == "application/vnd.google-apps.folder":
                print(ColorText.bcolors.ENDC, end='')

    def get_type(drive_items, item_name):
        desired_item = list(filter(lambda i: i['name'] == item_name, drive_items))
        if len(desired_item) == 0:
            print("File/Folder does not exist")
        else:
            print(desired_item[0]['mimeType'])

    def record_filenames(drive_items):
        content = "\n".join(map(lambda i: i['name'], drive_items))
        with open('filenames.txt', 'w') as f:
            f.write(content)

    def download_file(drive_items, item_name):
        desired_item = list(filter(lambda i: i['name'] == item_name, drive_items))
        if len(desired_item) == 0:
            print("File/Folder does not exist")
        else:
            request = service.files().get_media(fileId=desired_item[0]['id'])
            fh = io.FileIO(item_name, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                print("Download %d%%." % int(status.progress() * 100))

    while online.value:
        items = results.value.get('files', [])

        options = {
            'cd': lambda cmd: go_into_folder(items, " ".join(cmd[1:])),
            'typeof': lambda cmd: get_type(items, " ".join(cmd[1:])),
            'download': lambda cmd: download_file(items, " ".join(cmd[1:])),
            'ls': lambda _: print_items(items),
            'quit': lambda _: exit(0),
            'switch': lambda _: remove_login_token(),
            'current': lambda _: print(folder_stack.value[0]),
            'record': lambda _: record_filenames(items),
            'exec': lambda cmd: subprocess.call(" ".join(cmd[1:]), shell=True)
        }

        autocomplete_options = list(options.keys()) + list(map(lambda i: i['name'], items))
        pathway = "/".join(map(lambda d: d[0], reversed(folder_stack.value)))
        user_input = prompt(f"GDrive ∞/{pathway}> ",
                            history=FileHistory('history.txt'),
                            completer=AutoCompleter(autocomplete_options),
                            ).strip().split(' ')
        if user_input[0] in options:
            options[user_input[0]](user_input)
        else:
            print(f"Unknown command {user_input[0]}")


def login(creds: ReferenceVar[Any]):
    """
    Performs Google login and saves login information in a token.
    """
    if creds.value and creds.value.expired and creds.value.refresh_token:
        creds.value.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        creds.value = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open('token.pickle', 'wb') as token:
        pickle.dump(creds.value, token)


def start():
    """
    The first window of the GDrive CLI. Logs a user into a Google account.
    If a login token already exists, then this step is skipped and goes to the file system.
    """
    creds: ReferenceVar[Any] = ReferenceVar()
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds.value = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    while not creds.value or not creds.value.valid:
        options = {
            "login": lambda: login(creds),
            "quit": lambda: exit(0)
        }
        user_input = prompt('GDrive ∞> ',
                            history=FileHistory('history.txt'),
                            completer=AutoCompleter(list(options.keys())),
                            ).strip()
        if user_input in options:
            options[user_input]()
            main(creds.value)
        else:
            print("Invalid input")
    else:
        main(creds.value)


if __name__ == "__main__":
    start()
