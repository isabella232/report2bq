#Copyright 2020 Google LLC
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
from __future__ import annotations

import json

from google.oauth2 import credentials
from typing import Any, Dict

from classes import decorators
from classes.abstract_credentials import AbstractCredentials
from classes.abstract_datastore import AbstractDatastore
from classes.cloud_storage import Cloud_Storage
from classes.report_type import Type


class Credentials(AbstractCredentials):
  """Cloud connected credentials handler

  This extends and implements the AbstractCredentials for credentials held
  in Firestore or GCS on the cloud.
  """
  def __init__(self, email: str=None, project: str=None) -> Credentials:
      self._email=email
      self._project=project

  @property
  def datastore(self) -> AbstractDatastore:
    """The datastore property."""
    from classes.firestore import Firestore
    return Firestore()

  @property
  def project_credentials(self) -> Dict[str, Any]:
    """The project credentials.

    TODO: Remove the GCS check when fully migrated to Firestore."""
    return self.datastore.get_document(type=Type._ADMIN,
                                       id='auth', key='client_secret') or \
      json.loads(Cloud_Storage.fetch_file(bucket=self.bucket,
                                          file='client_secrets.json'))

  @property
  def token_details(self) -> Dict[str, Any]:
    """The users's refresh and access token."""
    # TODO: Remove the GCS check when fully migrated to Firestore.
    return self.datastore.get_document(type=Type._ADMIN, id='auth',
                                       key=self.encode_key(self._email)) or \
      json.loads(Cloud_Storage.fetch_file(bucket=self.bucket,
                                          file=self.client_token))

  @property
  def bucket(self) -> str:
    """The GCS bucket containing credentials."""
    # TODO: Remove when fully migrated to Firestore.
    return f'{self._project}-report2bq-tokens'

  @property
  def client_token(self) -> str:
    """The name of the token file in GCS."""
    # TODO: Remove when fully migrated to Firestore.
    return f'{self._email}_user_token.json'

  def store_credentials(self, creds: credentials.Credentials) -> None:
    """Stores the credentials.

    This function uses the datastore to store the user credentials for later.

    Args:
        creds (credentials.Credentials): the user credentials."""
    # TODO: Remove the GCS write when fully migrated to Firestore.
    if self._email:
      key = self.encode_key(self._email)
      refresh_token_details = {
        'access_token': creds.token,
        'refresh_token': creds.refresh_token,
        '_key': key
      }
      self.datastore.update_document(type=Type._ADMIN, id='auth',
                                     new_data={ key:
                                                json.loads(creds.to_json())})
      Cloud_Storage.write_file(
        bucket=self.bucket, file=self.client_token,
        data=json.dumps(refresh_token_details).encode('utf-8'))
