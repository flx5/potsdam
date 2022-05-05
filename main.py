import argparse
import random
import threading
import time
from datetime import date
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

URL='https://egov.potsdam.de/tnv/bgr'

# TODO Configure long timeouts


class ContactData(NamedTuple):
    gender: str
    first_name: str
    last_name: str
    email: str
    phone: str


class PostRequest(NamedTuple):
    address: str
    data: dict

    def submit(self):
        return requests.post(self.address, data=self.data).text


def institute_selection():
    # Auswahlseite des Amtes
    response = requests.get(URL).text
    soup = BeautifulSoup(response, 'html.parser')
    form = soup.find('form', id='contextForm')

    PGUTSMSC = form.find('input', attrs={'name': 'PGUTSMSC'}).attrs['value']
    TCSID = form.find('input', attrs={'name': 'TCSID'}).attrs['value']

    service_center_div: Tag = soup.find('div', string='Bürgerservicecenter').parent
    submit_button = service_center_div.find('button', string='Termin vereinbaren')
    SUBMIT_BUTTON_NAME = submit_button.attrs['name']

    action_url = urljoin(URL, form.attrs['action'])

    post_response = requests.post(action_url, data={
        'PGUTSMSC': PGUTSMSC,
        'TCSID': TCSID,
        SUBMIT_BUTTON_NAME: ''
    })

    return post_response.text

def service_selection(response):
    services_response = BeautifulSoup(response, 'html.parser')

    form = services_response.find('form', id='contextForm')
    action_url = urljoin(URL, form.attrs['action'])

    post_data = {}

    for input in form.find_all('input', type='hidden'):
        post_data[input.attrs['name']] = input.attrs['value']

    for input in form.find_all('select'):
        post_data[input.attrs['name']] = '0'

    label = form.find('label', string='Beantragung eines Personalausweises')

    personalausweis_input_name = form.find(id=label.attrs['for']).attrs['name']
    post_data[personalausweis_input_name] = 1

    post_data['ACTION_CONCERNSELECT_NEXT'] = ''

    return requests.post(action_url, data=post_data).text

def additional_information(response):
    additional_information_response = BeautifulSoup(response, 'html.parser')
    form = additional_information_response.find('form', id='contextForm')
    action_url = urljoin(URL, form.attrs['action'])

    post_data = {}

    for input in form.find_all('input', type='hidden'):
        post_data[input.attrs['name']] = input.attrs['value']

    post_data['ACTION_CONCERNCOMMENTS_NEXT'] = ''

    return requests.post(action_url, data=post_data).text

def is_day_button_available(button: Tag):
    timestamp = int(button.attrs['name'].rsplit('||', 1)[-1]) / 1000
    button_date = date.fromtimestamp(timestamp)

    # Filter out same day
    if button_date <= date.today():
        return False

    # TODO Optionally filter out more days


    button_text = button.find(class_='ekolCalendarFreeTimeContainer').string

    if button_text == 'geschlossen' or button_text == '0 frei':
        return False

    return True

def init_post_data(form):
    post_data = {}

    for input in form.find_all('input', type='hidden'):
        post_data[input.attrs['name']] = input.attrs['value']

    return post_data

def date_selection(response):
    soup = BeautifulSoup(response, 'html.parser')

    date_buttons = list(filter(is_day_button_available, soup.findAll('button', class_='eKOLCalendarButtonDay')))

    if len(date_buttons) == 0:
        return None

    chosen_button = random.choice(date_buttons)

    form = soup.find('form', id='contextForm')
    action_url = urljoin(URL, form.attrs['action'])

    post_data = init_post_data(form)
    post_data[chosen_button.attrs['name']] = ''

    return PostRequest(action_url, post_data)

def time_selection(response):
    soup = BeautifulSoup(response, 'html.parser')
    form = soup.find('form', id='contextForm')
    action_url = urljoin(URL, form.attrs['action'])

    time_select = form.find('select', id='ekolcalendartimeselectbox')

    # Keine Termine verfügbar
    if time_select is None:
        return None

    post_data = init_post_data(form)

    options = time_select.findAll('option')
    options = filter(lambda option: option.attrs['value'] != '', options)

    chosen_time = random.choice(list(options))

    post_data[time_select.attrs['name']] = chosen_time.attrs['value']

    submit_button_name = form.find(id='ekolcalendarpopupdayauswahlbuttoncontainer').button['name']
    post_data[submit_button_name] = ''

    return PostRequest(action_url, post_data)


def personal_information(response, contact_data: ContactData):
    soup = BeautifulSoup(response, 'html.parser')
    form = soup.find('form', id='contextForm')
    action_url = urljoin(URL, form.attrs['action'])

    post_data = init_post_data(form)

    post_data['ANREDE'] = contact_data.gender
    post_data['VORNAME'] = contact_data.first_name
    post_data['NACHNAME'] = contact_data.last_name
    post_data['TELEFON'] = contact_data.phone
    post_data['EMAIL'] = contact_data.email
    post_data['ACTION_USERDATA_NEXT'] = ''

    return PostRequest(action_url, post_data)


def confirm(response):
    soup = BeautifulSoup(response, 'html.parser')
    form = soup.find('form', id='contextForm')
    action_url = urljoin(URL, form.attrs['action'])

    post_data = init_post_data(form)
    post_data['ACTION_CONFIRM_NEXT'] = ''

    return PostRequest(action_url, post_data)

def check_success(response):
    soup = BeautifulSoup(response, 'html.parser')
    messages = soup.find(id='infomsglist').findChildren('li')

    failed = any(filter(lambda li: li.string == 'Der Termin ist nicht mehr frei.', messages))
    return not failed

def saveSuccessResponse(response):
    filename = str(threading.get_ident()) + '-success-' + str(time.time()) + ".html"
    Path(filename).write_text(response)
    print('Saved under ' + filename)

def thread_func(event: threading.Event, contact_data: ContactData):
    while not event.is_set():
        response = institute_selection()
        response = service_selection(response)
        response = additional_information(response)
        response = date_selection(response)

        if response is None:
            print('Keine Termine verfügbar')
            break

        response = time_selection(response.submit())

        if response is None:
            print('Keine Termine verfügbar')
            break

        response = personal_information(response.submit(), contact_data).submit()
        response = confirm(response).submit()

        if check_success(response):
            saveSuccessResponse(response)
            break

        time.sleep(10)

    event.set()


def init_argparse() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(

        usage="%(prog)s [OPTIONS]",

    )

    parser.add_argument(
        "-v", "--version", action="version",
        version = f"{parser.prog} version 1.0.0"
    )

    parser.add_argument("-g", "--gender", choices=['frau', 'herr', 'x', 'firma'], required=True)
    parser.add_argument("--vorname", type=str, required=True)
    parser.add_argument("--nachname", type=str, required=True)
    parser.add_argument("--email", type=str, required=True)
    parser.add_argument("--phone", type=str, required=True)

    return parser

def run(contact_data: ContactData):
    event = threading.Event()
    threads = list()

    for index in range(10):
        thread = threading.Thread(target=thread_func, args=(event,contact_data,))
        threads.append(thread)
        thread.start()

    print('Threads started.... Grab a cup of tea while you wait...')

    for thread in threads:
        thread.join()




def main():
    parser = init_argparse()

    args = parser.parse_args()

    contact_data = ContactData(gender=args.gender, first_name=args.vorname, last_name=args.nachname, email=args.email, phone=args.phone)
    run(contact_data)


def test_date_selection():
    input = Path('data/date_selection.html').read_text()

    request = date_selection(input)

    assert request is not None
    assert 'TCSID' in request.data
    assert 'PGUTSMSC' in request.data

def test_time_selection():
    input = Path('data/time_selection.html').read_text()

    request = time_selection(input)

    assert request is not None
    assert 'TCSID' in request.data
    assert 'PGUTSMSC' in request.data
    assert 'ekolCalendarTimeSelect' in request.data
    assert 'ACTION_CALENDARVIEW274156||POPUP_TIME_OK||1654207200000' in request.data

    assert request.data['ekolCalendarTimeSelect'] == '1654256100000'

def test_personal_information():
    input = Path('data/personal_information.html').read_text()
    request = personal_information(input, ContactData('frau', 'Erika', 'Musterfrau', 'erika.mustermann@local', '000'))

    assert request is not None
    assert 'TCSID' in request.data
    assert 'PGUTSMSC' in request.data

def test_confirm():
    input = Path('data/confirm.html').read_text()
    request = confirm(input)

    assert request is not None
    assert 'TCSID' in request.data
    assert 'PGUTSMSC' in request.data

    assert request.data['TCSID'] == '_ANEhrLUBhRmgsMVFHa2AzcWMjOzU4JXdLcWQgVnlMcUM5cmcs'
    assert request.data['PGUTSMSC'] == 'AAAAAABIAAAAOQABAAEAAAAABgVLUGV2YXNiZXdsb2tlAAAAAAAAAAAAAAAAAAAAAAALAAAADQAAAA8BOjn3VKVB1gAICAgAFAAUAgFLUAAAAA0AAAAPATo59wgHS1AAAjY0MTCyNDY3NDUzNDNldmFzYmV3bG9rZQAAAAsAAAAAAAAAAAAAAABUpUHWAAgICAAUBANLUA::'

def test_check_success_fail():
    input = Path('data/not_available_anymore.html').read_text()
    was_successful = check_success(input)
    assert was_successful is False

if __name__ == '__main__':
    main()
