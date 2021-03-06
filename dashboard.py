import json
import datetime
from flask import Flask, jsonify
from flask.templating import render_template
from jenkinsapi.artifact import Artifact
from jenkinsapi.custom_exceptions import NoBuildData
import os

from jenkinsapi.jenkins import Jenkins
from requests.exceptions import ConnectionError


JOB_URL_ENDING = "testReport/api/python"
app = Flask(__name__)


def get_jenkins():
    return Jenkins(get_config()['sources']['jenkins']['url'])


def get_jenkins_api():
    return Jenkins(get_config()['sources']['jenkins-api']['url'],
                   username=os.environ['JENKINS_USER'], password=os.environ['JENKINS_PASS'])


def get_config():
    return json.load(open('config.json'))


def get_item_config(build_name):
    config = get_config()
    if config.has_key('items') and config['items'].has_key(build_name):
        return config['items'][build_name]
    return {}


@app.route('/')
def index():
    config_data = get_config()
    screens_count = len(config_data['screens'])
    return render_template(
        'index.html', config=config_data, json_config=json.dumps(config_data), screens_count=screens_count)


@app.route('/jenkins_results/<build_name>', methods=['GET'])
def get_build_data(build_name):
    jenkins_instance = get_jenkins()
    item_config = get_item_config(build_name)
    if jenkins_instance is not None:
        build = jenkins_instance[build_name]
    else:
        raise ConnectionError("Connection with Jenkins failed")

    last_build = build.get_last_build()
    last_build_number = build.get_last_buildnumber()
    child_runs = last_build.get_matrix_runs()
    child_runs_count = 0
    results_url = last_build.get_result_url()
    if results_url.endswith(JOB_URL_ENDING):
        results_url = results_url[:results_url.find(JOB_URL_ENDING)]

    failed_runs = []
    success_runs = []
    return_val = {
        'name': build_name,
        'status': last_build.get_status(),
        'hours_ago': get_time_ago(last_build.get_timestamp()),
    }

    if item_config.has_key('artifact'):
        output = Artifact('output', item_config['artifact'], last_build).get_data()
        return_val['artifact_output'] = output
    else:
        has_next = True
        while has_next:
            try:
                current_build = child_runs.next()
            except StopIteration:
                has_next = False

            if has_next:
                child_runs_count += 1
                if current_build.get_number() == last_build_number\
                        and current_build.get_status() == 'FAILURE' or current_build.get_status() == 'UNSTABLE':
                    failed_runs.append({
                        'name': current_build.name.split('\xbb')[1].split(',')[0]
                    })
                elif current_build.get_number() == last_build_number and current_build.get_status() == 'SUCCESS'\
                        and (build_name.endswith("dev") or build_name.endswith("ios")):
                    success_runs.append({
                        'name': current_build.name.split('\xbb')[1].split(',')[0]
                    })

    return_val['results_url'] = results_url
    return_val['failed_runs'] = failed_runs
    return_val['has_failed_runs'] = (len(failed_runs) != 0)
    return_val['success_runs'] = success_runs
    return_val['has_success_runs'] = (len(success_runs) != 0)
    return_val['child_runs_count'] = child_runs_count
    return_val['failure_percentage'] = len(failed_runs) * 100 / child_runs_count if (child_runs_count != 0) else 100

    try:
        last_success = get_time_ago(build.get_last_stable_build().get_timestamp()),
    except NoBuildData:
        last_success = '???'

    return_val['last_success'] = last_success

    return jsonify(return_val)


@app.route('/jenkins_api_results/<build_name>', methods=['GET'])
def get_build_data_api(build_name):
    jenkins_instance = get_jenkins_api()
    if jenkins_instance is not None:
        build = jenkins_instance[build_name]
    else:
        raise ConnectionError("Connection with Jenkins failed")

    last_build = build.get_last_build()
    last_build_number = build.get_last_buildnumber()
    child_runs = last_build.get_matrix_runs()
    child_runs_count = 0
    failed_runs = []

    has_next = True
    while has_next:
        try:
            current_build = child_runs.next()
        except StopIteration:
            has_next = False

        if has_next:
            child_runs_count += 1
            if current_build.get_number() == last_build_number \
                    and (current_build.get_status() == 'FAILURE' or current_build.get_status() == 'UNSTABLE'):
                failed_runs.append({
                    'name': current_build.name.split('\xbb')[1].split(',')[0]
                })

    return_val = {
        'name': build_name,
        'status': last_build.get_status(),
        'hours_ago': get_time_ago(last_build.get_timestamp()),
        'failed_runs': failed_runs,
        'has_failed_runs': (len(failed_runs) != 0),
        'child_runs_count': child_runs_count,
        'failure_percentage': len(failed_runs) * 100 / child_runs_count if (len(failed_runs) != 0) else 0
    }

    try:
        last_success = get_time_ago(build.get_last_stable_build().get_timestamp()),
    except NoBuildData:
        last_success = '???'

    return_val['last_success'] = last_success

    return jsonify(return_val)


def get_time_ago(run_date):
    return int((datetime.datetime.utcnow().replace(tzinfo=None)
         - run_date.replace(tzinfo=None)).total_seconds() / 3600)

if __name__ == '__main__':
    app.debug = True
    app.run()
