# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from googleapiclient import discovery as gdiscovery
from classes.services import Service
from classes import discovery
from classes.sa360_report_validation import sa360_validator_factory

import csv
import dataclasses
import dataclasses_json
import enum
import io
import json
import logging
import os
import random
import stringcase
import uuid

# Class Imports
from typing import Any, Dict, List, Tuple

from classes import discovery
from classes.cloud_storage import Cloud_Storage
from classes.credentials import Credentials
from classes.report_manager import ReportManager
from classes.report_type import Type
from classes.sa360_report_validation import sa360_validator_factory
from classes.scheduler import Scheduler
from classes.services import Service


class Validity(enum.Enum):
    VALID = 'valid'
    INVALID = 'invalid'
    UNDEFINED = ''

    def __repr__(self):
        return self.value

    def __str__(self):
        return self.value

@dataclasses_json.dataclass_json
@dataclasses.dataclass
class Validation(object):
    agency: str = None
    advertiser: str = None
    conversionMetric: Validity = Validity.UNDEFINED
    revenueMetric: bool = Validity.UNDEFINED

    @classmethod
    def keys(cls):
        return list(Validation.__dataclass_fields__.keys())

class SA360Manager(ReportManager):
  report_type = Type.SA360_RPT
  sa360 = None
  sa360_service = None
  saved_column_names = {}
  actions = {
    'list',
    'show',
    'add',
    'delete',
    'validate',
    'install',
  }

  def manage(self, **kwargs) -> Any:
    project = kwargs['project']
    email = kwargs.get('email')
    self.bucket=f'{project}-report2bq-sa360-manager'

    if kwargs.get('api_key') is not None:
      os.environ['API_KEY'] = kwargs['API_KEY']

    if 'name' in kwargs:
      report_name = kwargs['name']
    elif 'file' in kwargs:
      report_name = kwargs['file'].split('/')[-1].split('.')[0]
    else:
      report_name = None

    args = {
      'report': report_name,
      'file': kwargs.get('file'),
      'project': project,
      'email': email,
      **kwargs,
    }

    return self._get_action(kwargs.get('action'))(**args)

  def validate(self, project: str, email: str,
               file: str=None, gcs_stored: bool=False, **unused) -> None:
    sa360_report_definitions = \
      self.firestore.get_document(self.report_type, '_reports')
    validation_results = []

    sa360_objects = \
      self._get_sa360_objects(
        file=file, gcs_stored=gcs_stored, project=project,
        email=email)

    for sa360_object in sa360_objects:
      if sa360_object == '_reports': continue
      creds = Credentials(project=project, email=sa360_object['email'])
      sa360_service = \
        discovery.get_service(service=Service.SA360, credentials=creds)

      (valid, validation) = \
        self._file_based(sa360_report_definitions, sa360_object, sa360_service)
      validation_results.append(validation)

    if validation_results:
      csv_output = f'{file}-validation.csv'
      if gcs_stored:
        csv_bytes = io.StringIO()
        writer = csv.DictWriter(
          csv_bytes, fieldnames=Validation.keys(), quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows([r.to_dict() for r in validation_results])
        Cloud_Storage(project=project, email=email).write_file(
          bucket=self.bucket,
          file=csv_output,
          data=csv_bytes.getvalue())

      else:
        with open(csv_output, 'w') as csv_file:
          writer = csv.DictWriter(
            csv_file, fieldnames=Validation.keys(), quoting=csv.QUOTE_ALL)
          writer.writeheader()
          writer.writerows([r.to_dict() for r in validation_results])

  def _get_sa360_objects(self, file: str, project: str, email: str,
                         gcs_stored: bool=False) -> List[Dict[str, Any]]:
    if file:
      if gcs_stored:
        content = Cloud_Storage(project=project,
                                email=email).fetch_file(bucket=self.bucket,
                                                        file=file)
        sa360_objects = json.loads(content)
      else:
        with open(file) as rpt:
          sa360_objects = json.loads(''.join(rpt.readlines()))

    else:
      sa360_objects = self.firestore.list_documents(self.report_type)

    return sa360_objects

  def _file_based(
    self, sa360_report_definitions: Dict[str, Any], report: Dict[str, Any],
    sa360_service: gdiscovery.Resource) -> Tuple[bool, Dict[str, Any]]:
    logging.info(
      'Validating %s (%s/%s) on report %s', report.get("agencyName", "-"),
      report["AgencyId"], report["AdvertiserId"], report["report"])

    target_report = sa360_report_definitions[report['report']]
    validator = \
      sa360_validator_factory.SA360ValidatorFactory().get_validator(
        report_type=target_report['report']['reportType'],
        sa360_service=sa360_service,
        agency=report['AgencyId'], advertiser=report['AdvertiserId'])
    report_custom_columns = \
      [column['name'] for column in target_report['parameters'] \
        if 'is_list' in column]
    valid = True
    validation = Validation(report['AgencyId'], report['AdvertiserId'])

    for report_custom_column in report_custom_columns:
      if report[report_custom_column]:
        (valid_column, name) = validator.validate(report[report_custom_column])
        valid = valid and valid_column
        validity = Validity.UNDEFINED
        if not valid:
          validity = Validity.INVALID
        elif report[report_custom_column]['value']:
          validity = Validity.VALID

        setattr(
          validation, stringcase.camelcase(report_custom_column), validity)
        if not valid_column and name:
          logging.info(
            f'  Field {report_custom_column} - {report[report_custom_column]}: '
            f'{valid_column}, did you mean "{name}"')
        else:
          logging.info(
            f'  Field {report_custom_column} - {report[report_custom_column]}: '
            f'{valid_column}')

    if len(set(report_custom_columns)) != len(report_custom_columns):
      valid = False

    return (valid, validation)

  def install(self, project: str, email: str,
    file: str=None, gcs_stored: bool=False, **unused) -> None:
    if not self.scheduler:
      logging.warn(
        'No scheduler is available: jobs will be stored but not scheduled.')

    results = []
    random.seed(uuid.uuid4())

    runners = self._get_sa360_objects(file, project, email, gcs_stored)
    sa360_report_definitions = \
      self.firestore.get_document(self.report_type, '_reports')

    for runner in runners:
      id = f"{runner['report']}_{runner['AgencyId']}_{runner['AdvertiserId']}"

      creds = Credentials(project=project, email=runner['email'])
      sa360_service = \
        discovery.get_service(service=Service.SA360, credentials=creds)
      (valid, validity) = self._file_based(
        sa360_report_definitions=sa360_report_definitions,
        report=runner, sa360_service=sa360_service)

      if valid:
        logging.info('Valid report: %s', id)
        self.firestore.update_document(type=self.report_type,
                                      id=id, new_data=runner)

        if self.scheduler:
          if not (description := runner.get('description')):
            description = ( \
              f'{runner["title"] if "title" in runner else runner["report"]}: '
              f'{runner["agencyName"]}/{runner["advertiserName"]}')
            runner['description'] = description

          results.append(self._schedule_job(project=project,
                                            runner=runner, id=id))
      else:
        logging.info('Invalid report: %s', id)
        results.append(f'{id} - Validation failed: {validity}')

    if results:
      self._output_results(
        results=results, project=project, email=email, gcs_stored=gcs_stored,
        file=file)
