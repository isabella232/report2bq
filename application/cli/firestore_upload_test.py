# Copyright 2021 Google LLC
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

import json
import unittest
from unittest import mock

from classes import local_datastore
from classes.report_type import Type
from cli import firestore_upload

from copy import deepcopy
from typing import Any, Callable, Dict, Mapping

CLASS_UNDER_TEST = 'cli.firestore_upload'


class FirestoreUploadTest(unittest.TestCase):
  def setUp(self) -> None:
    self.valid_source = {'test_root': {'a': 'A', 'b': 'B'}}
    self.open = mock.mock_open(read_data=json.dumps(self.valid_source))
    self.mock_datastore = mock.MagicMock()
    self.mock_datastore.update_document.return_value = None

  def test_good_unencoded(self):
    with mock.patch(f'{CLASS_UNDER_TEST}.open', self.open):
      with mock.patch.object(local_datastore.LocalDatastore,
                             'update_document',
                             return_value=None) as mock_method:
        event = {
          'key': 'key',
          'file': 'test.json',
          'encode_key': False,
          'local_store': True,
        }
        _ = firestore_upload.upload(**event)
        self.open.assert_called_with('test.json', 'r')
        self.open().read.assert_called()
        mock_method.assert_called()
        mock_method.assert_called_with(Type._ADMIN, id='key',
                                       new_data=self.valid_source)

  def test_good_encoded(self):
    with mock.patch(f'{CLASS_UNDER_TEST}.open', self.open):
      with mock.patch.object(local_datastore.LocalDatastore,
                             'update_document',
                             return_value=None) as mock_method:
        event = {
          'key': 'luke@skywalker.com',
          'file': 'test.json',
          'encode_key': True,
          'local_store': True,
        }
        _ = firestore_upload.upload(**event)
        self.open.assert_called_with('test.json', 'r')
        self.open().read.assert_called()
        mock_method.assert_called()
        expected = deepcopy(self.valid_source)
        expected['test_root']['_key'] = 'test_root'
        expected['dGVzdF9yb290'] = expected.pop('test_root')

        mock_method.assert_called_with(Type._ADMIN, id='luke@skywalker.com',
                                       new_data=expected)

